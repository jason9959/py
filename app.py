import streamlit as st
import yfinance as yf
import matplotlib.pyplot as plt
import datetime
import re
import pandas as pd
import numpy as np

# 1. 웹페이지 기본 설정
st.set_page_config(page_title="통합 포트폴리오 대시보드", layout="wide")

# ==========================================
# [사전 정의] 주요 종목 검색용 데이터베이스
# ==========================================
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
    "459580.KS": "KODEX 미국반도체MV"
}

def resolve_ticker(user_input):
    """입력받은 한글명/티커를 정규 티커로 변환하는 도우미 함수"""
    if not user_input:
        return None
    cleaned = user_input.strip()

    if re.fullmatch(r'[\u3131-\u318E]+', cleaned):
        return None

    cleaned_upper = cleaned.upper()
    if cleaned_upper in STOCK_DICT:
        return cleaned_upper

    for ticker, name in STOCK_DICT.items():
        if cleaned.lower() in name.lower() or cleaned_upper in ticker:
            return ticker

    return cleaned_upper

def calculate_rebalanced_portfolio(df_prices, target_weights, rebalance_type, static_freq=None, abs_sum_threshold=None, single_dev_threshold=None, init_cash=10000.0, invest_type="거치식", dca_amount=0.0, dca_freq="매월"):
    """
    일별 주가 데이터와 목표 비중, 리밸런싱 규칙, 투자 방식(거치식/적립식)에 따라 포트폴리오 자산 가치 및 총 투입 원금 시리즈를 계산
    """
    dates = df_prices.index
    n_days = len(dates)
    
    portfolio_values = np.zeros(n_days)
    invested_capital = np.zeros(n_days)  # 총 투입 원금 추적용
    
    # 초기 세팅
    current_cash_allocations = init_cash * target_weights
    initial_prices = df_prices.iloc[0].values
    shares = current_cash_allocations / initial_prices
    
    portfolio_values[0] = init_cash
    invested_capital[0] = init_cash
    
    current_total_invested = init_cash
    last_rebal_prices = initial_prices.copy()
    
    for t in range(1, n_days):
        curr_date = dates[t]
        prev_date = dates[t-1]
        current_prices = df_prices.iloc[t].values
        
        # ------------------------------------------
        # [추가] 적립식 투자 처리 (주기별 추가 자금 투입)
        # ------------------------------------------
        if invest_type == "적립식" and dca_amount > 0:
            is_dca_day = False
            if dca_freq == "매월":
                if curr_date.month != prev_date.month:
                    is_dca_day = True
            elif dca_freq == "매분기":
                curr_q = (curr_date.month - 1) // 3
                prev_q = (prev_date.month - 1) // 3
                if curr_q != prev_q:
                    is_dca_day = True
            elif dca_freq == "매년":
                if curr_date.year != prev_date.year:
                    is_dca_day = True
            
            if is_dca_day:
                # 추가 적립금을 목표 비중대로 매수
                add_shares = (dca_amount * target_weights) / current_prices
                shares += add_shares
                current_total_invested += dca_amount
        
        # 현재 자산 가치 평가
        current_asset_values = shares * current_prices
        current_total_val = np.sum(current_asset_values)
        portfolio_values[t] = current_total_val
        invested_capital[t] = current_total_invested
        
        # ------------------------------------------
        # 리밸런싱 판정 로직
        # ------------------------------------------
        do_rebalance = False
        
        if rebalance_type == "정적 리밸런싱":
            if static_freq == "매일":
                do_rebalance = True
            elif static_freq == "월간":
                if curr_date.month != prev_date.month:
                    do_rebalance = True
            elif static_freq == "분기":
                curr_q = (curr_date.month - 1) // 3
                prev_q = (prev_date.month - 1) // 3
                if curr_q != prev_q:
                    do_rebalance = True
            elif static_freq == "반기":
                curr_h = 1 if curr_date.month <= 6 else 2
                prev_h = 1 if prev_date.month <= 6 else 2
                if curr_h != prev_h:
                    do_rebalance = True
            elif static_freq == "연간":
                if curr_date.year != prev_date.year:
                    do_rebalance = True

        elif rebalance_type == "동적 리밸런싱":
            price_changes_pct = (current_prices - last_rebal_prices) / last_rebal_prices * 100.0
            
            abs_sum = np.sum(np.abs(price_changes_pct))
            cond1 = (abs_sum_threshold is not None) and (abs_sum >= abs_sum_threshold)
            
            cond2 = False
            if single_dev_threshold is not None and single_dev_threshold > 0:
                cond2 = np.any(np.abs(price_changes_pct) > single_dev_threshold)
                
            if cond1 or cond2:
                do_rebalance = True
                
        if do_rebalance:
            shares = (current_total_val * target_weights) / current_prices
            last_rebal_prices = current_prices.copy()
            
    return pd.Series(portfolio_values, index=dates), pd.Series(invested_capital, index=dates)

# ==========================================
# [사이드바] 메인 모드 선택 및 실행 버튼
# ==========================================
st.sidebar.title("📌 대시보드 메뉴")
app_mode = st.sidebar.selectbox(
    "실행할 기능을 선택하세요:",
    ["1. 다중 종목 상대 수익률 비교 (기준 100)", "2. 포트폴리오 자산배분 백테스트"]
)

# 👉 기능 선택 드롭다운 바로 밑으로 실행 버튼 이동
st.sidebar.markdown("---")
main_run_button = st.sidebar.button("🚀 선택한 기능 실행하기", use_container_width=True)
st.sidebar.markdown("---")

# ==========================================
# [사이드바] 리밸런싱 옵션 (기능 2 전용)
# ==========================================
rebalance_type = "정적 리밸런싱"
static_freq = "매일"
abs_sum_threshold = None
single_dev_threshold = None

if app_mode == "2. 포트폴리오 자산배분 백테스트":
    st.sidebar.subheader("⚙️ 2-1. 리밸런싱 기준 설정")

    rebalance_type = st.sidebar.selectbox(
        "리밸런싱 방식을 선택하세요:",
        ["정적 리밸런싱", "동적 리밸런싱"]
    )

    if rebalance_type == "정적 리밸런싱":
        static_freq = st.sidebar.selectbox(
            "리밸런싱 주기 선택:",
            ["매일", "월간", "분기", "반기", "연간"]
        )
    elif rebalance_type == "동적 리밸런싱":
        st.sidebar.caption("💡 리밸런싱 시점 대비 가격 변동 기준으로 실행합니다.")
        abs_sum_threshold = st.sidebar.number_input(
            "1. 전 종목 변동률 절대값 합계 임계값 (%) [필수]",
            min_value=0.1, value=10.0, step=0.5,
            help="각 종목의 변동률(|ΔP/P|) 절대값 총합이 이 값 이상이면 리밸런싱을 진행합니다."
        )
        single_dev_input = st.sidebar.text_input(
            "2. 개별 종목 변동률 임계값 (%) [선택]",
            value="",
            placeholder="예: 5.0 (미입력 시 미적용)"
        )
        if single_dev_input.strip():
            try:
                single_dev_threshold = float(single_dev_input)
            except ValueError:
                st.sidebar.error("개별 종목 변동률에는 숫자만 입력해 주세요.")

    st.sidebar.markdown("---")

# ==========================================
# 기능 1: 다중 종목 상대 수익률 비교 (기준 100)
# ==========================================
if app_mode == "1. 다중 종목 상대 수익률 비교 (기준 100)":
    st.title("📊 다중 종목 상대 성과 비교 (공통 기준일 = 100)")
    st.markdown("시작/종료 날짜를 선택한 뒤, **종목 1 ~ 10**에 티커나 종목명(삼성전자, AAPL 등)을 입력하세요.")

    st.sidebar.header("🔍 조회 조건 설정")

    # [STEP 1] 날짜 범위 설정
    st.sidebar.subheader("📅 조회 기간 선택")
    default_start = datetime.date(2026, 1, 1)
    default_end = datetime.date.today()
    start_date = st.sidebar.date_input("1-1. 시작 날짜", default_start)
    end_date = st.sidebar.date_input("1-2. 종료 날짜", default_end)

    st.sidebar.markdown("---")

    # [STEP 2] 종목 1~10 입력 수집 (기본값 빈값)
    st.sidebar.subheader("📈 비교 종목 입력 (최대 10개)")

    input_stock_list = []

    for i in range(10):
        slot_label = f"종목 {i+1}"
        val = st.sidebar.text_input(
            slot_label, 
            value="", 
            key=f"stock_input_{i+1}",
            placeholder="티커 또는 한글 종목명"
        )

        resolved_t = resolve_ticker(val)
        if resolved_t:
            input_stock_list.append({
                "slot": slot_label,
                "raw_input": val,
                "ticker": resolved_t
            })

    # [STEP 3] 유효성 검사 및 중복 처리
    ordered_target_tickers = []
    ticker_to_slot_map = {}

    for item in input_stock_list:
        tk = item["ticker"]
        if tk not in ordered_target_tickers:
            ordered_target_tickers.append(tk)
            ticker_to_slot_map[tk] = item["slot"]

    # ==========================================
    # [STEP 4] 데이터 조회 및 시각화 파이프라인
    # ==========================================
    if start_date >= end_date:
        st.error("시작 날짜는 종료 날짜보다 앞서야 합니다.")
    elif not ordered_target_tickers:
        st.warning("최소 1개 이상의 올바른 종목을 사이드바에 입력해 주세요.")
    else:
        if main_run_button:
            with st.spinner("Yahoo Finance에서 실시간 데이터를 불러오는 중..."):
                try:
                    df_raw = yf.download(ordered_target_tickers, start=start_date, end=end_date)["Close"]

                    if isinstance(df_raw, pd.Series):
                        df_raw = df_raw.to_frame(name=ordered_target_tickers[0])

                    existing_in_order = [t for t in ordered_target_tickers if t in df_raw.columns]
                    common_df = df_raw[existing_in_order].dropna()

                    if not common_df.empty and len(common_df) > 1:
                        final_tickers = list(common_df.columns)
                        base_date = common_df.index[0].strftime('%Y-%m-%d')

                        # 개별 종목 지수화 (단일 종목 기준)
                        indexed_df = (common_df / common_df.iloc[0]) * 100

                        st.subheader(f"📈 상대 성과 추이 그래프 (공통 기준일: {base_date} = 100)")

                        fig, ax = plt.subplots(figsize=(12, 6))
                        plt.style.use('seaborn-v0_8-whitegrid')

                        ax.axhline(100, color='gray', linestyle='--', linewidth=1.2, alpha=0.7, label="Base (100)")

                        # 개별 종목 라인 출력
                        for tk in final_tickers:
                            slot_name = ticker_to_slot_map.get(tk, "")
                            display_name = STOCK_DICT.get(tk, tk).split(' (')[0]
                            ax.plot(
                                indexed_df.index, 
                                indexed_df[tk], 
                                label=f"[{slot_name}] {tk} ({display_name})", 
                                linewidth=2
                            )

                        ax.set_title(f'Indexed Performance Comparison ({base_date} ~ {end_date})', fontsize=15, fontweight='bold')
                        ax.set_xlabel('Date', fontsize=11)
                        ax.set_ylabel('Indexed Value (Base = 100)', fontsize=11)
                        ax.legend(fontsize=10, loc='upper left')

                        st.pyplot(fig)

                        # 요약 카드
                        st.subheader("📌 공통 기간 최종 수익률 요약")
                        cols = st.columns(min(len(final_tickers), 5))

                        for idx, tk in enumerate(final_tickers):
                            slot_name = ticker_to_slot_map.get(tk, "")
                            current_idx_val = indexed_df[tk].iloc[-1]
                            return_pct = current_idx_val - 100

                            col_target = cols[idx % 5]
                            col_target.metric(
                                label=f"{slot_name}: {tk}", 
                                value=f"{current_idx_val:.2f}", 
                                delta=f"{return_pct:+.2f}%"
                            )

                        st.subheader("최근 지수화 데이터 (기준일 = 100)")
                        st.dataframe(indexed_df.tail(10))

                    else:
                        st.error("입력하신 종목들의 공통 거래일 주가 데이터가 부족합니다. 날짜 범위를 조정해 보세요.")
                except Exception as e:
                    st.error(f"데이터 처리 중 오류가 발생했습니다: {e}")

# ==========================================
# 기능 2: 포트폴리오 자산배분 백테스트 및 위험 분석
# ==========================================
elif app_mode == "2. 포트폴리오 자산배분 백테스트":
    st.title("💼 포트폴리오 자산배분 백테스트 & 위험 분석")
    st.markdown("설정한 자산 비중과 리밸런싱 조건에 따른 **포트폴리오 총자산 성장 추이**와 **CAGR, MDD, 샤프 지수** 등을 분석합니다.")

    # ------------------------------------------
    # [추가] 2-2. 투자 방식 선택 옵션 (거치식 / 적립식)
    # ------------------------------------------
    st.sidebar.subheader("💡 2-2. 투자 방식 선택")
    invest_type = st.sidebar.radio(
        "투자 방식을 선택하세요:",
        ["거치식", "적립식"],
        horizontal=True
    )
    st.sidebar.markdown("---")

    st.sidebar.header("🔍 백테스트 조건 설정")

    # [STEP 1] 날짜 및 초기 투자금 설정 (투자 방식별 동적 입력창)
    st.sidebar.subheader("📅 기간 및 투자 자금")
    default_start = datetime.date(2021, 1, 1)
    default_end = datetime.date.today()
    start_date = st.sidebar.date_input("2-3-1. 시작 날짜", default_start, key="bt_start")
    end_date = st.sidebar.date_input("2-3-2. 종료 날짜", default_end, key="bt_end")
    
    init_balance = st.sidebar.number_input(
        "2-3-3. 초기 투자금 (거치금액) ($ 또는 원)", 
        value=10000, 
        step=1000,
        help="시작일에 일시로 투입하는 금액입니다."
    )

    # [추가] 적립식 선택 시 적립 금액 및 적립 주기 옵션 제공
    dca_amount = 0.0
    dca_freq = "매월"
    if invest_type == "적립식":
        dca_amount = st.sidebar.number_input(
            "2-3-4. 적립 금액 ($ 또는 원)", 
            value=1000, 
            step=100,
            help="설정한 주기마다 추가로 적립 투입할 금액입니다."
        )
        dca_freq = st.sidebar.selectbox(
            "2-3-5. 적립 주기",
            ["매월", "매분기", "매년"]
        )

    st.sidebar.markdown("---")

    # [STEP 2] 종목 및 비중 입력 (기본값 빈값)
    st.sidebar.subheader("⚖️ 포트폴리오 자산 비중 (%)")
    st.sidebar.caption("비중의 합이 100%가 되도록 설정하세요.")

    input_portfolio = []
    
    for i in range(5):
        col_t, col_w = st.sidebar.columns([2, 1])
        with col_t:
            val = st.text_input(f"종목 {i+1}", value="", placeholder="티커/명칭", key=f"bt_tk_{i+1}")
        with col_w:
            weight = st.number_input(f"비중%", value=0, min_value=0, max_value=100, step=5, key=f"bt_wt_{i+1}")
        
        resolved_t = resolve_ticker(val)
        if resolved_t and weight > 0:
            input_portfolio.append({
                "ticker": resolved_t,
                "weight": weight
            })

    total_weight = sum([item["weight"] for item in input_portfolio])
    
    st.sidebar.markdown(f"**현재 총 비중 합계:** `{total_weight}%`")
    if total_weight != 100 and len(input_portfolio) > 0:
        st.sidebar.warning("⚠️ 비중 합계가 100%가 되도록 조정해 주세요.")

    # ==========================================
    # [STEP 3] 백테스트 연산 및 데이터 처리
    # ==========================================
    if main_run_button:
        if start_date >= end_date:
            st.error("시작 날짜는 종료 날짜보다 앞서야 합니다.")
        elif not input_portfolio:
            st.warning("최소 1개 이상의 유효한 종목과 0% 초과의 비중을 입력해 주세요.")
        elif total_weight != 100:
            st.error(f"비중 합계가 {total_weight}%입니다. 100%가 되도록 변경 후 실행해 주세요.")
        else:
            with st.spinner("과거 주가 데이터 수집 및 포트폴리오 백테스팅 중..."):
                try:
                    bt_tickers = [item["ticker"] for item in input_portfolio]
                    weights = np.array([item["weight"] / 100.0 for item in input_portfolio])

                    df_raw = yf.download(bt_tickers, start=start_date, end=end_date)["Close"]

                    if isinstance(df_raw, pd.Series):
                        df_raw = df_raw.to_frame(name=bt_tickers[0])

                    existing_tickers = [t for t in bt_tickers if t in df_raw.columns]
                    df_clean = df_raw[existing_tickers].dropna()

                    if df_clean.empty or len(df_clean) < 2:
                        st.error("해당 기간의 공통 거래일 데이터가 부족합니다.")
                    else:
                        # 리밸런싱 및 적립 연산 시뮬레이션
                        portfolio_val, invested_cap = calculate_rebalanced_portfolio(
                            df_clean, weights, rebalance_type, static_freq, abs_sum_threshold, single_dev_threshold, 
                            init_cash=init_balance, invest_type=invest_type, dca_amount=dca_amount, dca_freq=dca_freq
                        )

                        # 지표 산출
                        total_days = (df_clean.index[-1] - df_clean.index[0]).days
                        years = total_days / 365.25
                        
                        final_val = portfolio_val.iloc[-1]
                        final_invested = invested_cap.iloc[-1]  # 최종 투입 원금
                        
                        # 총 수익률 = (최종 자산 / 총 투입 원금 - 1) * 100
                        total_return_pct = ((final_val / final_invested) - 1) * 100
                        cagr = (((final_val / init_balance) ** (1 / years)) - 1) * 100 if years > 0 else 0

                        # 일별 수익률 기반 변동성 및 샤프 지수
                        portfolio_daily_return = portfolio_val.pct_change().dropna()
                        volatility = portfolio_daily_return.std() * (252 ** 0.5) * 100
                        risk_free_rate = 0.02
                        mean_annual_return = portfolio_daily_return.mean() * 252
                        sharpe_ratio = (mean_annual_return - risk_free_rate) / (volatility / 100) if volatility != 0 else 0

                        # MDD (Maximum Drawdown)
                        peak = portfolio_val.cummax()
                        drawdown = (portfolio_val - peak) / peak
                        mdd = drawdown.min() * 100

                        # --------------------------------------
                        # 결과 시각화
                        # --------------------------------------
                        st.subheader("📌 핵심 성과 지표 (Key Metrics)")
                        st.caption(f"투자 방식: **{invest_type}** " + (f"({dca_freq} {dca_amount:,.0f} 적립)" if invest_type == "적립식" else "") + f" | 적용된 리밸런싱: **{rebalance_type}** " + (f"({static_freq})" if static_freq else ""))

                        m1, m2, m3, m4, m5, m6 = st.columns(6)
                        
                        m1.metric("최종 자산 평가액", f"{final_val:,.0f}")
                        m2.metric("총 투입 원금", f"{final_invested:,.0f}")
                        m3.metric("총 수익률", f"{total_return_pct:+.2f}%")
                        m4.metric("CAGR (연평균 성장률)", f"{cagr:.2f}%")
                        m5.metric("MDD (최대 낙폭)", f"{mdd:.2f}%")
                        m6.metric("Sharpe Ratio", f"{sharpe_ratio:.2f}")

                        st.markdown("---")

                        # 차트 1: 자산 가치 상승 곡선 (+ 적립식인 경우 총 투입 원금 선 함께 표시)
                        st.subheader("📈 포트폴리오 자산 성장 추이")
                        fig_pf, ax_pf = plt.subplots(figsize=(12, 5))
                        plt.style.use('seaborn-v0_8-whitegrid')

                        ax_pf.plot(portfolio_val.index, portfolio_val, label="Portfolio Value (평가액)", color="#1f77b4", linewidth=2.5)
                        
                        # 적립식일 때는 투입 원금 선을 함께 시각화하여 비주얼 강화
                        if invest_type == "적립식":
                            ax_pf.plot(invested_cap.index, invested_cap, label="Total Invested (투입 원금)", color="gray", linestyle="--", linewidth=1.8)

                        ax_pf.set_title(f'Portfolio Growth [{invest_type}] ({df_clean.index[0].strftime("%Y-%m-%d")} ~ {df_clean.index[-1].strftime("%Y-%m-%d")})', fontsize=14, fontweight='bold')
                        ax_pf.set_ylabel("Asset Value", fontsize=11)
                        ax_pf.legend(loc='upper left')
                        st.pyplot(fig_pf)

                        # 차트 2: Drawdown (낙폭 차트)
                        st.subheader("📉 Drawdown (고점 대비 낙폭)")
                        fig_dd, ax_dd = plt.subplots(figsize=(12, 3))
                        ax_dd.fill_between(drawdown.index, drawdown * 100, 0, color="red", alpha=0.3)
                        ax_dd.plot(drawdown.index, drawdown * 100, color="red", linewidth=1)
                        ax_dd.set_ylabel("Drawdown (%)", fontsize=11)
                        ax_dd.set_ylim(min(drawdown * 100) * 1.1, 5)
                        st.pyplot(fig_dd)

                        # 구성 포트폴리오 요약 표
                        st.subheader("📋 설정 포트폴리오 비중")
                        pf_df = pd.DataFrame(input_portfolio)
                        pf_df["name"] = pf_df["ticker"].map(lambda x: STOCK_DICT.get(x, x))
                        pf_df["weight"] = pf_df["weight"].map(lambda x: f"{x}%")
                        st.table(pf_df[["ticker", "name", "weight"]])

                except Exception as e:
                    st.error(f"백테스트 계산 중 오류가 발생했습니다: {e}")
