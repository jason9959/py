
import streamlit as st
import yfinance as yf
import matplotlib.pyplot as plt
import datetime
import re
import pandas as pd
import numpy as np
import requests
import base64
import json


GITHUB_OWNER = "jason9959"
GITHUB_REPO = "py"
GITHUB_FILE_PATH = "saved_data/simulations.json"

"""
    GitHub의 saved_data/simulations.json을 읽어서
    Python dict 형태로 반환한다.
"""

def load_saved_simulations():
    
    try:
        token = st.secrets["GITHUB_TOKEN"]

        url = (
            f"https://api.github.com/repos/"
            f"{GITHUB_OWNER}/{GITHUB_REPO}/contents/{GITHUB_FILE_PATH}"
        )

        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
        }

        response = requests.get(url, headers=headers, timeout=10)

        if response.status_code != 200:
            st.error(
                f"GitHub 파일 읽기 실패 "
                f"(HTTP {response.status_code})"
            )
            return {}

        data = response.json()

        # GitHub API는 파일 내용을 Base64로 반환한다.
        content = base64.b64decode(data["content"]).decode("utf-8")

        return json.loads(content)

    except Exception as e:
        st.error(f"저장 데이터 읽기 오류: {e}")
        return {}

saved_simulations = load_saved_simulations()

st.write("GitHub 저장 데이터:")
st.write(saved_simulations)
"""

# =========================================================
# 1. 웹페이지 기본 설정
# =========================================================
st.set_page_config(page_title="통합 포트폴리오 대시보드", layout="wide")

if "last_backtest_result" not in st.session_state:
    st.session_state["last_backtest_result"] = None
# =========================================================
# 주요 종목 검색용 데이터베이스
# =========================================================
STOCK_DICT = {
    # 미국 주식/ETF
    "AAPL": "Apple Inc. (애플)",
    "MSFT": "Microsoft Corporation (마이크로소프트)",
    "NVDA": "NVIDIA Corporation (엔비디아)",
    "TSLA": "Tesla Inc. (테슬라)",
    "AMZN": "Amazon.com Inc. (아마존)",
    "GOOGL": "Alphabet Inc. (구글)",
    "META": "Meta Platforms (메타)",
    "SPY": "SPDR S&P 500 ETF Trust",
    "QQQ": "Invesco QQQ Trust",
    "SCHD": "Schwab U.S. Dividend Equity ETF",

    # 한국 주식/ETF (.KS)
    "005930.KS": "삼성전자 (Samsung Electronics)",
    "000660.KS": "SK하이닉스 (SK Hynix)",
    "379800.KS": "KODEX 미국S&P500TR",
    "005380.KS": "현대차 (Hyundai Motor)",
    "035420.KS": "NAVER (네이버)",
    "035720.KS": "카카오 (Kakao)",
    "459580.KS": "KODEX 미국반도체MV",
}


def resolve_ticker(user_input):
    """한글명/티커를 정규 티커로 변환."""
    if not user_input:
        return None

    cleaned = user_input.strip()

    # 자음/모음만 입력한 경우는 유효 티커로 취급하지 않음
    if re.fullmatch(r'[\u3131-\u318E]+', cleaned):
        return None

    cleaned_upper = cleaned.upper()

    if cleaned_upper in STOCK_DICT:
        return cleaned_upper

    for ticker, name in STOCK_DICT.items():
        if cleaned.lower() in name.lower() or cleaned_upper in ticker:
            return ticker

    return cleaned_upper


# =========================================================
# 가격 데이터 처리
# =========================================================
def download_adjusted_close(tickers, start_date, end_date):
    """
    Yahoo Finance에서 Adj Close를 가져온다.

    yfinance의 end는 일반적으로 exclusive이므로 사용자가 입력한 종료일을
    포함시키기 위해 하루를 더해서 요청한다.
    """
    if not tickers:
        raise ValueError("조회할 종목이 없습니다.")

    request_end = pd.Timestamp(end_date) + pd.Timedelta(days=1)

    raw = yf.download(
        tickers,
        start=pd.Timestamp(start_date),
        end=request_end,
        auto_adjust=False,
        progress=False,
        threads=True,
        group_by="column",
    )

    if raw is None or raw.empty:
        raise ValueError("Yahoo Finance에서 데이터를 가져오지 못했습니다.")

    if isinstance(raw.columns, pd.MultiIndex):
        if "Adj Close" not in raw.columns.get_level_values(0):
            raise ValueError("Yahoo Finance 응답에 Adj Close 데이터가 없습니다.")
        prices = raw["Adj Close"].copy()
    else:
        if "Adj Close" not in raw.columns:
            raise ValueError("Yahoo Finance 응답에 Adj Close 데이터가 없습니다.")
        prices = raw[["Adj Close"]].copy()
        prices.columns = [tickers[0]]

    if isinstance(prices, pd.Series):
        prices = prices.to_frame(name=tickers[0])

    # 사용자가 입력한 순서를 유지
    available = [t for t in tickers if t in prices.columns]
    if not available:
        raise ValueError("입력한 종목의 가격 데이터가 없습니다.")

    prices = prices[available].copy()
    prices.index = pd.to_datetime(prices.index).tz_localize(None)
    prices = prices.sort_index()

    # 숫자형으로 변환
    for col in prices.columns:
        prices[col] = pd.to_numeric(prices[col], errors="coerce")

    return prices


def prepare_common_price_data(tickers, start_date, end_date):
    """
    모든 종목의 실제 데이터 기간을 확인하여
    공통기간 = 가장 늦은 시작일 ~ 가장 빠른 종료일로 결정한다.

    공통기간 안의 종목별 누락 날짜는 직전 가격으로 채운다.
    미래 가격을 과거로 가져오는 backfill은 하지 않는다.
    """
    prices = download_adjusted_close(tickers, start_date, end_date)

    # 요청한 모든 종목의 데이터가 존재하는지 확인
    missing_tickers = [t for t in tickers if t not in prices.columns]
    if missing_tickers:
        raise ValueError(
            "다음 종목의 주가 데이터를 조회할 수 없습니다: "
            + ", ".join(missing_tickers)
        )

    data_start_dates = {}
    data_end_dates = {}

    for ticker in tickers:
        s = prices[ticker].dropna()
        if s.empty:
            raise ValueError(f"{ticker}의 유효한 주가 데이터가 없습니다.")
        data_start_dates[ticker] = s.index.min()
        data_end_dates[ticker] = s.index.max()

    common_start = max(data_start_dates.values())
    common_end = min(data_end_dates.values())

    if common_start >= common_end:
        raise ValueError(
            "모든 종목의 공통 데이터 기간이 없습니다. "
            "조회 기간이나 종목을 확인해 주세요."
        )

    # 공통기간 내 실제 관측일 전체를 합친 날짜축
    # (각 시장의 거래일이 다를 수 있으므로 union 사용)
    raw_common = prices.loc[
        (prices.index >= common_start) & (prices.index <= common_end),
        tickers,
    ].copy()

    # 종목별 직전 가격으로 누락 보정
    # 공통 시작일 이전의 마지막 가격을 사용할 수 있도록 원본에서 ffill 후 slice
    filled = prices[tickers].ffill()

    common_dates = raw_common.index.union(
        filled.loc[
            (filled.index >= common_start) & (filled.index <= common_end)
        ].index
    ).sort_values()

    common_df = filled.reindex(common_dates).ffill()
    common_df = common_df.loc[
        (common_df.index >= common_start) & (common_df.index <= common_end),
        tickers,
    ]

    # 공통 시작일에 어떤 종목도 미래가격을 소급 사용하지 않았는지 확인
    if common_df.isna().any().any():
        bad_cols = common_df.columns[common_df.isna().any()].tolist()
        raise ValueError(
            "공통 데이터 시작 시점 이전의 가격이 없어 "
            f"직전 가격 보정이 불가능한 종목이 있습니다: {bad_cols}"
        )

    common_df = common_df.dropna(how="all")

    if len(common_df) < 2:
        raise ValueError("공통 데이터 기간의 날짜가 2개 미만입니다.")

    return common_df, data_start_dates, data_end_dates, common_start, common_end


# =========================================================
# 적립/리밸런싱 일정
# =========================================================
def make_schedule_dates(first_date, freq):
    """
    최초 데이터 날짜를 기준으로 일정한 간격의 예정일을 생성한다.
    매월 = 1개월, 매분기 = 3개월, 매반기 = 6개월, 매년 = 12개월.
    pandas DateOffset을 사용하므로 8/27 -> 9/27 -> 10/27처럼 진행한다.
    """
    if freq == "매월":
        months = 1
    elif freq == "매분기":
        months = 3
    elif freq == "반기":
        months = 6
    elif freq == "매년":
        months = 12
    else:
        return []

    dates = []
    k = 1
    while True:
        scheduled = pd.Timestamp(first_date) + pd.DateOffset(months=months * k)
        dates.append(scheduled)
        k += 1
        # 실제 데이터보다 충분히 뒤로 넘어가면 종료
        if scheduled > pd.Timestamp(first_date) + pd.DateOffset(months=months * 10000):
            break
        # 호출 측에서 실제 범위와 교집합을 사용하므로 여기서는 생성하지 않고
        # 아래 helper를 통해 실제 날짜에 매핑한다.
        if k > 10000:
            break
    return dates


def calculate_single_asset_comparison(
    prices,
    initial_investment,
    invest_type,
    dca_amount=0.0,
    dca_dates=None,
    name="Comparison",
):
    """
    포트폴리오와 동일한 초기 투자금/적립금을 사용하여
    비교 종목 1개를 100% 보유했을 때의 실제 평가액을 계산한다.

    거치식:
        최초일에 초기 투자금 전액으로 매수

    적립식:
        최초일에 초기 투자금 전액으로 매수하고,
        포트폴리오와 동일한 적립일마다 적립금 전액으로 추가 매수

    비교 종목에는 리밸런싱을 적용하지 않는다.
    """
    prices = prices.dropna()

    if prices.empty:
        return pd.Series(dtype=float)

    if initial_investment <= 0:
        raise ValueError("비교 종목의 초기 투자금은 0보다 커야 합니다.")

    first_price = float(prices.iloc[0])
    shares = float(initial_investment) / first_price
    values = []
    dca_dates = set(dca_dates or [])

    for i, (date, price) in enumerate(prices.items()):
        price = float(price)

        if i > 0 and invest_type == "적립식" and date in dca_dates:
            shares += float(dca_amount) / price

        values.append(shares * price)

    return pd.Series(values, index=prices.index, name=f"{name} Value")


def map_schedule_to_data_dates(data_index, first_date, freq):
    """
    최초 데이터 날짜 기준 예정일을 실제 데이터 날짜에 매핑한다.
    예정일이 데이터에 없으면 예정일 이후 가장 가까운 날짜를 선택한다.
    """
    if freq == "매일":
        return set(data_index[1:])

    if freq == "매월":
        months = 1
    elif freq == "매분기":
        months = 3
    elif freq == "반기":
        months = 6
    elif freq == "연간" or freq == "매년":
        months = 12
    else:
        return set()

    first_date = pd.Timestamp(first_date)
    data_index = pd.DatetimeIndex(data_index)

    mapped = set()

    k = 1
    while True:
        scheduled = first_date + pd.DateOffset(months=months * k)
        if scheduled > data_index[-1]:
            break

        # 예정일 이후 가장 가까운 데이터 날짜
        pos = data_index.searchsorted(scheduled, side="left")
        if pos < len(data_index):
            actual_date = data_index[pos]
            if actual_date > first_date:
                mapped.add(actual_date)

        k += 1
        if k > 10000:
            break

    return mapped


# =========================================================
# 포트폴리오 백테스트 엔진
# =========================================================
def calculate_rebalanced_portfolio(
    df_prices,
    target_weights,
    rebalance_type,
    static_freq=None,
    abs_sum_threshold=None,
    single_dev_threshold=None,
    init_cash=10000.0,
    invest_type="거치식",
    dca_amount=0.0,
    dca_freq="매월",
):
    """
    포트폴리오 백테스트.

    핵심 규칙:
    1) 초기 투자금은 최초 목표비율로 투자
    2) 동적 리밸런싱은 현재비중과 목표비중의 편차로 판단
       - 전체: sum(abs(current_weight-target_weight)) > threshold
       - 개별: any(abs(current_weight-target_weight)) > threshold
    3) 적립일에는 적립금 자체를 현재비중대로 배분
    4) 적립일과 리밸런싱일이 겹치면
       현재 평가액 + 적립금을 합친 총액을 목표비율로 리밸런싱
    5) 정적 리밸런싱은 최초 데이터 날짜를 기준으로
       1/3/6/12개월 간격으로 계산
    """
    dates = pd.DatetimeIndex(df_prices.index)
    n_days = len(dates)

    if n_days < 2:
        raise ValueError("백테스트에 필요한 데이터가 부족합니다.")

    target_weights = np.asarray(target_weights, dtype=float)

    if len(target_weights) != df_prices.shape[1]:
        raise ValueError("목표 비중과 종목 수가 일치하지 않습니다.")

    if not np.isclose(target_weights.sum(), 1.0):
        raise ValueError("목표 비중의 합은 100%여야 합니다.")

    if init_cash <= 0:
        raise ValueError("초기 투자금은 0보다 커야 합니다.")

    if invest_type == "적립식" and dca_amount <= 0:
        raise ValueError("적립식에서는 적립 금액이 0보다 커야 합니다.")

    prices = df_prices.to_numpy(dtype=float)
    n_assets = prices.shape[1]

    # 결과 시계열
    portfolio_values = np.zeros(n_days)
    invested_capital = np.zeros(n_days)
    contribution_series = np.zeros(n_days)

    # 거래/상태 기록
    records = []

    # 초기 투자
    shares = (init_cash * target_weights) / prices[0]
    current_total_invested = float(init_cash)

    portfolio_values[0] = init_cash
    invested_capital[0] = current_total_invested

    # 일정표
    dca_dates = set()
    if invest_type == "적립식":
        dca_dates = map_schedule_to_data_dates(dates, dates[0], dca_freq)

    static_rebalance_dates = set()
    if rebalance_type == "정적 리밸런싱":
        if static_freq == "매일":
            static_rebalance_dates = set(dates[1:])
        else:
            static_rebalance_dates = map_schedule_to_data_dates(
                dates, dates[0], static_freq
            )

    for t in range(1, n_days):
        curr_date = dates[t]
        current_prices = prices[t]

        # 1. 현재 보유자산 평가
        current_asset_values_before = shares * current_prices
        current_total_val_before = float(np.sum(current_asset_values_before))

        if current_total_val_before <= 0:
            raise ValueError(f"{curr_date.date()}의 포트폴리오 평가액이 0 이하입니다.")

        current_weights_before = (
            current_asset_values_before / current_total_val_before
        )

        # 2. 적립 예정 여부
        is_dca_day = curr_date in dca_dates

        # 3. 리밸런싱 판단
        do_rebalance = False
        rebalance_reason = ""

        if rebalance_type == "정적 리밸런싱":
            if curr_date in static_rebalance_dates:
                do_rebalance = True
                rebalance_reason = f"정적({static_freq})"

        elif rebalance_type == "동적 리밸런싱":
            deviation = np.abs(current_weights_before - target_weights)
            abs_sum_deviation_pct = float(np.sum(deviation) * 100.0)

            cond1 = (
                abs_sum_threshold is not None
                and abs_sum_deviation_pct > float(abs_sum_threshold)
            )

            cond2 = False
            max_single_deviation_pct = float(np.max(deviation) * 100.0)

            if single_dev_threshold is not None and single_dev_threshold > 0:
                cond2 = bool(
                    np.any(deviation * 100.0 > float(single_dev_threshold))
                )

            if cond1 or cond2:
                do_rebalance = True
                reasons = []
                if cond1:
                    reasons.append("전체편차")
                if cond2:
                    reasons.append("개별편차")
                rebalance_reason = "동적(" + ", ".join(reasons) + ")"
        else:
            raise ValueError("올바르지 않은 리밸런싱 방식입니다.")

        # 4. 적립 + 리밸런싱 처리
        contribution = 0.0

        if is_dca_day:
            contribution = float(dca_amount)
            current_total_invested += contribution

        if do_rebalance:
            # 적립일이면 기존 평가액 + 적립금을 합친 총액으로 목표비율 리밸런싱
            total_for_rebalance = current_total_val_before + contribution

            shares = (
                total_for_rebalance * target_weights
            ) / current_prices

        elif is_dca_day:
            # 리밸런싱이 없으면 적립금은 현재 보유비중대로 분배
            add_asset_values = contribution * current_weights_before
            add_shares = add_asset_values / current_prices
            shares = shares + add_shares

        # 5. 당일 최종 평가
        current_asset_values_after = shares * current_prices
        current_total_val = float(np.sum(current_asset_values_after))

        portfolio_values[t] = current_total_val
        invested_capital[t] = current_total_invested
        contribution_series[t] = contribution

        current_weights_after = (
            current_asset_values_after / current_total_val
        )

        records.append(
            {
                "date": curr_date,
                "portfolio_value": current_total_val,
                "invested_capital": current_total_invested,
                "contribution": contribution,
                "is_dca": is_dca_day,
                "is_rebalance": do_rebalance,
                "rebalance_reason": rebalance_reason,
                "pre_value": current_total_val_before,
                "pre_weight_deviation_sum_pct": float(
                    np.sum(np.abs(current_weights_before - target_weights)) * 100.0
                ),
                "pre_max_single_deviation_pct": float(
                    np.max(np.abs(current_weights_before - target_weights)) * 100.0
                ),
            }
        )

    return (
        pd.Series(portfolio_values, index=dates, name="Portfolio Value"),
        pd.Series(invested_capital, index=dates, name="Invested Capital"),
        pd.Series(contribution_series, index=dates, name="Contribution"),
        pd.DataFrame(records),
    )


# =========================================================
# 성과지표
# =========================================================
def calculate_xirr(cash_flows):
    """
    XIRR 계산.
    cash_flows: [(date, amount), ...]
    amount < 0 = 투자금, amount > 0 = 회수금/최종평가액
    """
    if not cash_flows:
        return np.nan

    cf = [(pd.Timestamp(d), float(v)) for d, v in cash_flows]
    values = np.array([v for _, v in cf], dtype=float)

    if not (np.any(values < 0) and np.any(values > 0)):
        return np.nan

    first_date = cf[0][0]

    def npv(rate):
        return sum(
            amount / ((1.0 + rate) ** ((date - first_date).days / 365.0))
            for date, amount in cf
        )

    # -99.99% ~ 매우 높은 수익률까지 탐색하여 부호가 바뀌는 구간 확보
    low = -0.9999
    f_low = npv(low)

    high = 1.0
    f_high = npv(high)

    for _ in range(100):
        if f_low * f_high <= 0:
            break
        high *= 2.0
        f_high = npv(high)
    else:
        return np.nan

    # 이분법
    for _ in range(200):
        mid = (low + high) / 2.0
        f_mid = npv(mid)

        if abs(f_mid) < 1e-9:
            return mid

        if f_low * f_mid <= 0:
            high = mid
            f_high = f_mid
        else:
            low = mid
            f_low = f_mid

    return (low + high) / 2.0


def calculate_cashflow_adjusted_returns(
    portfolio_val,
    contribution_series,
    risk_free_rate=0.02,
):
    """
    외부 현금 유입(적립금)의 영향을 제거한 일간 수익률을 계산한다.

    당일 적립금 C_t가 들어온 뒤의 평가액 V_t와 전일 평가액 V_{t-1}에 대해:
        adjusted_return_t = V_t / (V_{t-1} + C_t) - 1

    이렇게 계산하면 단순히 적립금을 넣었다는 이유로 MDD/Sharpe가
    왜곡되는 것을 줄일 수 있다.
    """
    values = portfolio_val.astype(float)
    contributions = contribution_series.reindex(values.index).fillna(0.0)

    adjusted_returns = []

    for i in range(1, len(values)):
        previous_value = float(values.iloc[i - 1])
        contribution = float(contributions.iloc[i])
        denominator = previous_value + contribution

        if denominator <= 0:
            adjusted_returns.append(0.0)
        else:
            adjusted_returns.append(float(values.iloc[i] / denominator - 1.0))

    adjusted_returns = pd.Series(
        adjusted_returns,
        index=values.index[1:],
        name="Cashflow Adjusted Daily Return",
    )

    # 시간가중 성장곡선
    growth = (1.0 + adjusted_returns).cumprod()
    growth = pd.concat(
        [pd.Series([1.0], index=[values.index[0]]), growth]
    )

    peak = growth.cummax()
    drawdown = growth / peak - 1.0
    mdd = float(drawdown.min() * 100.0)

    if adjusted_returns.empty or adjusted_returns.std(ddof=1) == 0:
        sharpe = 0.0
    else:
        annualized_return = float(adjusted_returns.mean() * 252)
        annualized_volatility = float(
            adjusted_returns.std(ddof=1) * np.sqrt(252)
        )
        sharpe = (
            (annualized_return - risk_free_rate)
            / annualized_volatility
        )

    return adjusted_returns, growth, drawdown, mdd, sharpe


def calculate_lump_sum_metrics(portfolio_val, init_balance, risk_free_rate=0.02):
    """거치식 성과지표."""
    values = portfolio_val.astype(float)

    if init_balance <= 0:
        raise ValueError("초기 투자금은 0보다 커야 합니다.")

    total_days = (values.index[-1] - values.index[0]).days
    years = total_days / 365.25

    final_val = float(values.iloc[-1])
    total_return_pct = (final_val / init_balance - 1.0) * 100.0

    cagr = (
        ((final_val / init_balance) ** (1.0 / years) - 1.0) * 100.0
        if years > 0 and final_val > 0
        else np.nan
    )

    daily_return = values.pct_change().dropna()

    if daily_return.empty or daily_return.std(ddof=1) == 0:
        sharpe = 0.0
        volatility = 0.0
    else:
        volatility = float(daily_return.std(ddof=1) * np.sqrt(252) * 100.0)
        annualized_return = float(daily_return.mean() * 252)
        sharpe = (
            (annualized_return - risk_free_rate)
            / (volatility / 100.0)
        )

    peak = values.cummax()
    drawdown = values / peak - 1.0
    mdd = float(drawdown.min() * 100.0)

    return {
        "final_val": final_val,
        "final_invested": float(init_balance),
        "total_return_pct": total_return_pct,
        "cagr": cagr,
        "mdd": mdd,
        "sharpe": float(sharpe),
        "volatility": volatility,
        "drawdown": drawdown,
    }


def calculate_dca_metrics(
    portfolio_val,
    invested_capital,
    contribution_series,
):
    """적립식 성과지표."""
    values = portfolio_val.astype(float)
    invested = invested_capital.astype(float)
    contributions = contribution_series.astype(float)

    final_val = float(values.iloc[-1])
    final_invested = float(invested.iloc[-1])

    total_return_pct = (
        (final_val / final_invested - 1.0) * 100.0
        if final_invested > 0
        else np.nan
    )

    # XIRR 현금흐름
    cash_flows = [(values.index[0], -float(invested.iloc[0]))]

    for date in values.index[1:]:
        contribution = float(contributions.loc[date])
        if contribution != 0:
            cash_flows.append((date, -contribution))

    # 최종 평가액 회수
    cash_flows.append((values.index[-1], final_val))

    xirr = calculate_xirr(cash_flows)

    (
        adjusted_returns,
        growth,
        drawdown,
        mdd,
        sharpe,
    ) = calculate_cashflow_adjusted_returns(values, contributions)

    return {
        "final_val": final_val,
        "final_invested": final_invested,
        "total_return_pct": total_return_pct,
        "xirr": xirr * 100.0 if not np.isnan(xirr) else np.nan,
        "mdd": mdd,
        "sharpe": sharpe,
        "drawdown": drawdown,
        "adjusted_returns": adjusted_returns,
        "growth": growth,
    }


# =========================================================
# 사이드바 - 메인 모드
# =========================================================
st.sidebar.title("📌 대시보드 메뉴")

app_mode = st.sidebar.selectbox(
    "실행할 기능을 선택하세요:",
    [
        "1. 다중 종목 상대 수익률 비교 (기준 100)",
        "2. 포트폴리오 자산배분 백테스트",
    ],
)

st.sidebar.markdown("---")
main_run_button = st.sidebar.button(
    "🚀 선택한 기능 실행하기",
    use_container_width=True,
)
st.sidebar.markdown("---")


# =========================================================
# 리밸런싱 옵션 (기능 2 전용)
# =========================================================
rebalance_type = "정적 리밸런싱"
static_freq = "매일"
abs_sum_threshold = None
single_dev_threshold = None

if app_mode == "2. 포트폴리오 자산배분 백테스트":
    st.sidebar.subheader("⚙️ 1. 리밸런싱 기준 설정")

    rebalance_type = st.sidebar.selectbox(
        "리밸런싱 방식을 선택하세요:",
        ["정적 리밸런싱", "동적 리밸런싱"],
    )

    if rebalance_type == "정적 리밸런싱":
        static_freq = st.sidebar.selectbox(
            "리밸런싱 주기 선택:",
            ["매일", "월간", "분기", "반기", "연간"],
        )

    elif rebalance_type == "동적 리밸런싱":
        st.sidebar.caption(
            "💡 목표 비중 대비 현재 자산 비중의 편차를 기준으로 실행합니다."
        )

        abs_sum_threshold = st.sidebar.number_input(
            "1. 전 종목 변동률 절대값 합계 임계값 (%) [필수]",
            min_value=0.1,
            value=10.0,
            step=0.5,
            help=(
                "각 종목의 현재 비중과 목표 비중 차이의 절대값 합계가 "
                "이 값을 초과하면 리밸런싱합니다."
            ),
        )

        single_dev_input = st.sidebar.text_input(
            "2. 개별 종목 변동률 임계값 (%) [선택]",
            value="",
            placeholder="예: 5.0 (미입력 시 미적용)",
        )

        if single_dev_input.strip():
            try:
                single_dev_threshold = float(single_dev_input)
                if single_dev_threshold <= 0:
                    st.sidebar.error(
                        "개별 종목 임계값은 0보다 커야 합니다."
                    )
                    single_dev_threshold = None
            except ValueError:
                st.sidebar.error(
                    "개별 종목 변동률에는 숫자만 입력해 주세요."
                )

    st.sidebar.markdown("---")


# =========================================================
# 기능 1: 다중 종목 상대 수익률 비교
# =========================================================
if app_mode == "1. 다중 종목 상대 수익률 비교 (기준 100)":

    st.title("📊 다중 종목 상대 성과 비교 (공통 기준일 = 100)")
    st.markdown(
        "시작/종료 날짜를 선택한 뒤, **종목 1 ~ 10**에 "
        "티커나 종목명(삼성전자, AAPL 등)을 입력하세요."
    )

    st.sidebar.header("🔍 조회 조건 설정")

    # STEP 1
    st.sidebar.subheader("📅 조회 기간 선택")

    default_end = datetime.date.today()
    default_start = default_end - datetime.timedelta(days=365)

    start_date = st.sidebar.date_input(
        "3-1. 시작 날짜",
        default_start,
        min_value=datetime.date(1900, 1, 1),
        max_value=datetime.date.today(),
        key="bt_start",
    )

    end_date = st.sidebar.date_input(
        "3-2. 종료 날짜",
        default_end,
        min_value=datetime.date(1900, 1, 1),
        max_value=datetime.date.today(),
        key="bt_end",
    )
       
    # default_start = datetime.date(2026, 1, 1)
    # default_end = datetime.date.today()
    
    # start_date = st.sidebar.date_input(
    #     "1-1. 시작 날짜",
    #     default_start,
    # )
    # end_date = st.sidebar.date_input(
    #     "1-2. 종료 날짜",
    #     default_end,
    # )

    st.sidebar.markdown("---")

    # STEP 2 - 최대 10종목
    st.sidebar.subheader("📈 비교 종목 입력 (최대 10개)")

    input_stock_list = []

    for i in range(10):
        slot_label = f"종목 {i+1}"

        val = st.sidebar.text_input(
            slot_label,
            value="",
            key=f"stock_input_{i+1}",
            placeholder="티커 또는 한글 종목명",
        )

        resolved_t = resolve_ticker(val)

        if resolved_t:
            input_stock_list.append(
                {
                    "slot": slot_label,
                    "raw_input": val,
                    "ticker": resolved_t,
                }
            )

    # STEP 3 - 중복 제거/검사
    ordered_target_tickers = []
    ticker_to_slot_map = {}
    duplicate_tickers = []

    for item in input_stock_list:
        tk = item["ticker"]

        if tk not in ordered_target_tickers:
            ordered_target_tickers.append(tk)
            ticker_to_slot_map[tk] = item["slot"]
        else:
            duplicate_tickers.append(tk)

    if duplicate_tickers:
        st.sidebar.warning(
            "⚠️ 중복 종목은 한 번만 비교합니다: "
            + ", ".join(dict.fromkeys(duplicate_tickers))
        )

    # STEP 4
    if start_date >= end_date:
        st.error("시작 날짜는 종료 날짜보다 앞서야 합니다.")

    elif not ordered_target_tickers:
        st.warning(
            "최소 1개 이상의 올바른 종목을 사이드바에 입력해 주세요."
        )

    elif main_run_button:
        with st.spinner(
            "Yahoo Finance에서 조정가격(Adj Close)을 불러오는 중..."
        ):
            try:
                common_df, starts, ends, common_start, common_end = (
                    prepare_common_price_data(
                        ordered_target_tickers,
                        start_date,
                        end_date,
                    )
                )

                final_tickers = list(common_df.columns)
                base_date = common_df.index[0].strftime("%Y-%m-%d")

                # 기준일 100
                indexed_df = (
                    common_df / common_df.iloc[0]
                ) * 100.0

                st.subheader(
                    f"📈 상대 성과 추이 그래프 "
                    f"(공통 기준일: {base_date} = 100)"
                )

                fig, ax = plt.subplots(figsize=(12, 6))

                ax.axhline(
                    100,
                    linestyle="--",
                    linewidth=1.2,
                    alpha=0.7,
                    label="Base (100)",
                )

                for tk in final_tickers:
                    slot_name = ticker_to_slot_map.get(tk, "")
                    display_name = STOCK_DICT.get(tk, tk).split(" (")[0]

                    ax.plot(
                        indexed_df.index,
                        indexed_df[tk],
                        label=f"[{slot_name}] {tk} ({display_name})",
                        linewidth=2,
                    )

                ax.set_title(
                    f"Indexed Performance Comparison "
                    f"({common_start.strftime('%Y-%m-%d')} ~ "
                    f"{common_end.strftime('%Y-%m-%d')})",
                    fontsize=15,
                    fontweight="bold",
                )
                ax.set_xlabel("Date", fontsize=11)
                ax.set_ylabel("Indexed Value (Base = 100)", fontsize=11)
                ax.legend(fontsize=10, loc="upper left")

                st.pyplot(fig)

                # 요약 카드
                st.subheader("📌 공통 기간 최종 수익률 요약")

                cols = st.columns(min(len(final_tickers), 5))

                for idx, tk in enumerate(final_tickers):
                    slot_name = ticker_to_slot_map.get(tk, "")
                    current_idx_val = float(indexed_df[tk].iloc[-1])
                    return_pct = current_idx_val - 100.0

                    col_target = cols[idx % 5]

                    col_target.metric(
                        label=f"{slot_name}: {tk}",
                        value=f"{current_idx_val:.2f}",
                        delta=f"{return_pct:+.2f}%",
                    )

                st.subheader("최근 지수화 데이터 (기준일 = 100)")
                st.dataframe(indexed_df.tail(10))

            except Exception as e:
                st.error(f"데이터 처리 중 오류가 발생했습니다: {e}")


# =========================================================
# 기능 2: 포트폴리오 자산배분 백테스트
# =========================================================
elif app_mode == "2. 포트폴리오 자산배분 백테스트":

    st.title("💼 포트폴리오 자산배분 백테스트 & 위험 분석")
    st.markdown(
        "설정한 자산 비중과 리밸런싱 조건에 따른 "
        "**포트폴리오 총자산 성장 추이**와 성과지표를 분석합니다."
    )

    # 투자 방식
    st.sidebar.subheader("💡 2. 투자 방식 선택")

    invest_type = st.sidebar.selectbox(
        "투자 방식을 선택하세요:",
        ["거치식", "적립식"],
    )

    st.sidebar.markdown("---")
    st.sidebar.header("🔍 백테스트 조건 설정")

    # STEP 1
    st.sidebar.subheader("📅 기간 및 투자 자금")

    default_end = datetime.date.today()
    default_start = default_end - datetime.timedelta(days=365)

    start_date = st.sidebar.date_input(
        "3-1. 시작 날짜",
        default_start,
        min_value=datetime.date(1900, 1, 1),
        max_value=datetime.date.today(),
        key="bt_start",
    )

    end_date = st.sidebar.date_input(
        "3-2. 종료 날짜",
        default_end,
        min_value=datetime.date(1900, 1, 1),
        max_value=datetime.date.today(),
        key="bt_end",
    )
       
    # default_start = datetime.date(2026, 1, 1)
    # default_end = datetime.date.today()
    
    # start_date = st.sidebar.date_input(
    #     "1-1. 시작 날짜",
    #     default_start,
    # )
    # end_date = st.sidebar.date_input(
    #     "1-2. 종료 날짜",
    #     default_end,
    # )
    init_balance = st.sidebar.number_input(
        "3-3. 초기 투자금 (거치금액) ($ 또는 원)",
        value=10000,
        min_value=1,
        step=1000,
        help="시작일에 일시로 투입하는 금액입니다.",
    )

    dca_amount = 0.0
    dca_freq = "매월"

    if invest_type == "적립식":
        dca_amount = st.sidebar.number_input(
            "2-3-4. 적립 금액 ($ 또는 원)",
            value=1000,
            min_value=1,
            step=100,
            help="설정한 주기마다 추가로 적립 투입할 금액입니다.",
        )

        dca_freq = st.sidebar.selectbox(
            "2-3-5. 적립 주기",
            ["매월", "매분기", "매년"],
        )

    st.sidebar.markdown("---")

    # 비교 종목 (선택)
    comparison_ticker_input = st.sidebar.text_input(
        "📊 비교 종목 (선택)",
        value="",
        placeholder="예: SPY 또는 종목명",
        key="bt_comparison_ticker",
        help=(
            "입력하면 포트폴리오와 동일한 초기 투자금/적립금으로 "
            "해당 종목을 100% 보유한 결과를 자산 성장 그래프에 함께 표시합니다. "
            "주가는 Adj Close를 사용합니다."
        ),
    )
    comparison_ticker = resolve_ticker(comparison_ticker_input)

    # STEP 2 - 최대 10종목
    st.sidebar.subheader("⚖️ 포트폴리오 자산 비중 (%)")
    st.sidebar.caption("최대 10종목 / 비중의 합이 정확히 100%가 되도록 설정하세요.")

    input_portfolio = []
    portfolio_tickers_seen = set()
    duplicate_portfolio_tickers = []

    for i in range(10):
        col_t, col_w = st.sidebar.columns([2, 1])

        with col_t:
            val = st.text_input(
                f"종목 {i+1}",
                value="",
                placeholder="티커/명칭",
                key=f"bt_tk_{i+1}",
            )

        with col_w:
            weight = st.number_input(
                f"비중%",
                value=0,
                min_value=0,
                max_value=100,
                step=5,
                key=f"bt_wt_{i+1}",
            )

        resolved_t = resolve_ticker(val)

        if resolved_t and weight > 0:
            if resolved_t in portfolio_tickers_seen:
                duplicate_portfolio_tickers.append(resolved_t)
            else:
                portfolio_tickers_seen.add(resolved_t)
                input_portfolio.append(
                    {
                        "ticker": resolved_t,
                        "weight": float(weight),
                    }
                )

    total_weight = sum(item["weight"] for item in input_portfolio)

    st.sidebar.markdown(
        f"**현재 총 비중 합계:** `{total_weight:.0f}%`"
    )

    if duplicate_portfolio_tickers:
        st.sidebar.error(
            "중복 종목이 있습니다: "
            + ", ".join(dict.fromkeys(duplicate_portfolio_tickers))
        )

    if total_weight != 100 and len(input_portfolio) > 0:
        st.sidebar.warning(
            "⚠️ 비중 합계가 100%가 되도록 조정해 주세요."
        )

    # STEP 3
    if main_run_button or st.session_state["last_backtest_result"] is not None:

        if start_date >= end_date:
            st.error("시작 날짜는 종료 날짜보다 앞서야 합니다.")

        elif not input_portfolio:
            st.warning(
                "최소 1개 이상의 유효한 종목과 0% 초과의 비중을 입력해 주세요."
            )

        elif duplicate_portfolio_tickers:
            st.error(
                "중복 종목을 제거한 후 다시 실행해 주세요."
            )

        elif total_weight != 100:
            st.error(
                f"비중 합계가 {total_weight:.0f}%입니다. "
                "100%가 되도록 변경 후 실행해 주세요."
            )

        elif invest_type == "적립식" and dca_amount <= 0:
            st.error("적립식의 적립 금액은 0보다 커야 합니다.")

        else:
            with st.spinner(
                "과거 조정가격(Adj Close) 데이터 수집 및 "
                "포트폴리오 백테스팅 중..."
            ):
                try:
                    bt_tickers = [
                        item["ticker"] for item in input_portfolio
                    ]
                    weights = np.array(
                        [item["weight"] / 100.0 for item in input_portfolio],
                        dtype=float,
                    )

                    (
                        df_clean,
                        data_starts,
                        data_ends,
                        common_start,
                        common_end,
                    ) = prepare_common_price_data(
                        bt_tickers,
                        start_date,
                        end_date,
                    )

                    # -----------------------------------------
                    # 선택한 비교 종목 데이터 준비
                    # -----------------------------------------
                    comparison_values = None
                    comparison_prices = None

                    if comparison_ticker:
                        comparison_df = download_adjusted_close(
                            [comparison_ticker],
                            common_start - pd.Timedelta(days=7),
                            common_end,
                        )

                        if comparison_ticker not in comparison_df.columns:
                            raise ValueError(
                                f"비교 종목 '{comparison_ticker}'의 가격 데이터를 가져오지 못했습니다."
                            )

                        comparison_prices = comparison_df[comparison_ticker].reindex(
                            df_clean.index
                        ).ffill()

                        if comparison_prices.isna().any():
                            raise ValueError(
                                f"비교 종목 '{comparison_ticker}'의 공통 백테스트 시작일 "
                                f"({common_start.strftime('%Y-%m-%d')})에 사용할 가격 데이터가 없습니다."
                            )

                    if main_run_button:
                        (        
                            portfolio_val,
                            invested_cap,
                            contribution_series,
                            event_df,
                        ) = calculate_rebalanced_portfolio(
                            df_clean,
                            weights,
                            rebalance_type,
                            static_freq,
                            abs_sum_threshold,
                            single_dev_threshold,
                            init_cash=float(init_balance),
                            invest_type=invest_type,
                            dca_amount=float(dca_amount),
                            dca_freq=dca_freq,
                        )

                    
                        st.session_state["last_backtest_result"] = {
                            "portfolio_val": portfolio_val.copy(),
                            "invested_cap": invested_cap.copy(),
                            "contribution_series": contribution_series.copy(),
                            "event_df": event_df.copy(),
                        }

                    else:
                    
                        result = st.session_state["last_backtest_result"]
                    
                        portfolio_val = result["portfolio_val"].copy()
                        invested_cap = result["invested_cap"].copy()
                        contribution_series = result["contribution_series"].copy()
                        event_df = result["event_df"].copy()
                    

                    # -----------------------------------------
                    # 비교 종목 평가액 계산
                    # -----------------------------------------
                    if comparison_ticker and comparison_prices is not None:
                        comparison_dca_dates = set(
                            event_df.loc[event_df["is_dca"], "date"]
                        )

                        comparison_values = calculate_single_asset_comparison(
                            prices=comparison_prices,
                            initial_investment=float(init_balance),
                            invest_type=invest_type,
                            dca_amount=float(dca_amount),
                            dca_dates=comparison_dca_dates,
                            name=comparison_ticker,
                        )

                    # -----------------------------------------
                    # 지표 산출
                    # -----------------------------------------
                    if invest_type == "거치식":
                        metrics = calculate_lump_sum_metrics(
                            portfolio_val,
                            float(init_balance),
                        )
                        drawdown = metrics["drawdown"]

                    else:
                        metrics = calculate_dca_metrics(
                            portfolio_val,
                            invested_cap,
                            contribution_series,
                        )
                        drawdown = metrics["drawdown"]

                    final_val = metrics["final_val"]
                    final_invested = metrics["final_invested"]
                    total_return_pct = metrics["total_return_pct"]

                    # -----------------------------------------
                    # 결과
                    # -----------------------------------------
                    st.subheader("📌 핵심 성과 지표 (Key Metrics)")

                    if invest_type == "적립식":
                        xirr_text = (
                            f"{metrics['xirr']:.2f}%"
                            if not np.isnan(metrics["xirr"])
                            else "계산 불가"
                        )

                        st.caption(
                            f"투자 방식: **적립식** "
                            f"({dca_freq} {dca_amount:,.0f} 적립) | "
                            f"적용된 리밸런싱: **{rebalance_type}** "
                            f"{f'({static_freq})' if static_freq else ''}"
                        )

                        m1, m2, m3, m4, m5, m6 = st.columns(6)

                        m1.metric(
                            "최종 자산 평가액",
                            f"{final_val:,.0f}",
                        )
                        m2.metric(
                            "총 투입 원금",
                            f"{final_invested:,.0f}",
                        )
                        m3.metric(
                            "총 수익률",
                            f"{total_return_pct:+.2f}%",
                        )
                        m4.metric(
                            "XIRR",
                            xirr_text,
                        )
                        m5.metric(
                            "MDD (현금흐름 조정)",
                            f"{metrics['mdd']:.2f}%",
                        )
                        m6.metric(
                            "Sharpe Ratio (현금흐름 조정)",
                            f"{metrics['sharpe']:.2f}",
                        )

                    else:
                        st.caption(
                            f"투자 방식: **거치식** | "
                            f"적용된 리밸런싱: **{rebalance_type}** "
                            f"{f'({static_freq})' if static_freq else ''}"
                        )

                        m1, m2, m3, m4, m5, m6 = st.columns(6)

                        m1.metric(
                            "최종 자산 평가액",
                            f"{final_val:,.0f}",
                        )
                        m2.metric(
                            "총 투입 원금",
                            f"{final_invested:,.0f}",
                        )
                        m3.metric(
                            "총 수익률",
                            f"{total_return_pct:+.2f}%",
                        )
                        m4.metric(
                            "CAGR (연평균 성장률)",
                            f"{metrics['cagr']:.2f}%",
                        )
                        m5.metric(
                            "MDD (최대 낙폭)",
                            f"{metrics['mdd']:.2f}%",
                        )
                        m6.metric(
                            "Sharpe Ratio",
                            f"{metrics['sharpe']:.2f}",
                        )

                    st.markdown("---")

                    # -----------------------------------------
                    # 차트 1
                    # -----------------------------------------
                    st.subheader("📈 포트폴리오 자산 성장 추이")

                    fig_pf, ax_pf = plt.subplots(figsize=(12, 5))

                    ax_pf.plot(
                        portfolio_val.index,
                        portfolio_val,
                        label="Portfolio Value (평가액)",
                        linewidth=2.5,
                    )

                    if comparison_values is not None:
                        ax_pf.plot(
                            comparison_values.index,
                            comparison_values,
                            label=f"Comparison: {comparison_ticker}",
                            linestyle="--",
                            linewidth=2.0,
                        )

                    if invest_type == "적립식":
                        ax_pf.plot(
                            invested_cap.index,
                            invested_cap,
                            label="Total Invested (투입 원금)",
                            linestyle="--",
                            linewidth=1.8,
                        )

                    ax_pf.set_title(
                        f'Portfolio Growth [{invest_type}] '
                        f'({df_clean.index[0].strftime("%Y-%m-%d")} ~ '
                        f'{df_clean.index[-1].strftime("%Y-%m-%d")})',
                        fontsize=14,
                        fontweight="bold",
                    )
                    ax_pf.set_ylabel("Asset Value", fontsize=11)
                    ax_pf.legend(loc="upper left")

                    st.pyplot(fig_pf)

                    # -----------------------------------------
                    # 차트 2 - 현금흐름 조정 여부에 맞는 drawdown
                    # -----------------------------------------
                    st.subheader("📉 Drawdown (고점 대비 낙폭)")

                    fig_dd, ax_dd = plt.subplots(figsize=(12, 3))

                    ax_dd.fill_between(
                        drawdown.index,
                        drawdown * 100,
                        0,
                        alpha=0.3,
                    )
                    ax_dd.plot(
                        drawdown.index,
                        drawdown * 100,
                        linewidth=1,
                    )

                    ax_dd.set_ylabel("Drawdown (%)", fontsize=11)

                    min_dd = float((drawdown * 100).min())
                    ax_dd.set_ylim(
                        min(min_dd * 1.1, -1),
                        5,
                    )

                    st.pyplot(fig_dd)

                    # -----------------------------------------
                    # 설정 포트폴리오
                    # -----------------------------------------
                    st.subheader("📋 설정 포트폴리오 비중")

                    pf_df = pd.DataFrame(input_portfolio)
                    pf_df["name"] = pf_df["ticker"].map(
                        lambda x: STOCK_DICT.get(x, x)
                    )
                    pf_df["weight"] = pf_df["weight"].map(
                        lambda x: f"{x:.0f}%"
                    )

                    st.table(
                        pf_df[["ticker", "name", "weight"]]
                    )

                    # -----------------------------------------
                    # 리밸런싱/적립 이벤트
                    # -----------------------------------------
                    if not event_df.empty:
                        event_view = event_df[
                            (event_df["is_dca"])
                            | (event_df["is_rebalance"])
                        ].copy()

                        if not event_view.empty:
                            st.subheader("📝 적립 / 리밸런싱 이벤트")

                            event_view = event_view[
                                [
                                    "date",
                                    "portfolio_value",
                                    "invested_capital",
                                    "contribution",
                                    "is_dca",
                                    "is_rebalance",
                                    "rebalance_reason",
                                    "pre_weight_deviation_sum_pct",
                                    "pre_max_single_deviation_pct",
                                ]
                            ]

                            event_view = event_view.rename(
                                columns={
                                    "date": "날짜",
                                    "portfolio_value": "최종 평가액",
                                    "invested_capital": "총 투입원금",
                                    "contribution": "당일 적립금",
                                    "is_dca": "적립일",
                                    "is_rebalance": "리밸런싱",
                                    "rebalance_reason": "사유",
                                    "pre_weight_deviation_sum_pct": "리밸런싱 전 전체 편차(%)",
                                    "pre_max_single_deviation_pct": "리밸런싱 전 최대 개별 편차(%)",
                                }
                            )

                            st.dataframe(
                                event_view,
                                use_container_width=True,
                            )

                except Exception as e:
                    st.error(
                        f"백테스트 계산 중 오류가 발생했습니다: {e}"
                    )
