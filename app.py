import datetime
import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf
import matplotlib.pyplot as plt

# Streamlit 페이지 기본 설정
st.set_page_config(page_title="통합 포트폴리오 대시보드", layout="wide")

# ==========================================
# 0. 공통 함수: 한글 이름 -> 티커 변환
# ==========================================
NAME_TO_TICKER = {
    "삼성전자": "005930.KS",
    "SK하이닉스": "000660.KS",
    "NAVER": "035420.KS",
    "카카오": "035720.KS",
    "애플": "AAPL",
    "마이크로소프트": "MSFT",
    "엔비디아": "NVDA",
    "아마존": "AMZN",
    "구글": "GOOGL",
    "테슬라": "TSLA",
    "S&P500": "SPY",
    "나스닥": "QQQ",
    "미국채10년": "IEF",
    "TLT": "TLT",
    "GLD": "GLD"
}

def resolve_ticker(input_str):
    clean_str = input_str.strip()
    return NAME_TO_TICKER.get(clean_str, clean_str)

# ==========================================
# 1. 백테스트 및 리밸런싱 계산 로직
# ==========================================
def calculate_rebalanced_portfolio(
    df, 
    weights, 
    strategy="정적 (주기적)", 
    period="매월", 
    threshold=0.05,
    initial_cash=10000000,
    investment_type="거치식",
    contribution_amount=0,
    contribution_freq="매월"
):
    """
    적립금 및 리밸런싱 반영 포트폴리오 백테스트 계산 함수
    """
    pct_change = df.pct_change().fillna(0)
    dates = df.index
    num_assets = len(weights)
    
    # 일별 자산 가치 및 총 포트폴리오 가치 기록 배열
    asset_values = np.zeros((len(dates), num_assets))
    portfolio_value = np.zeros(len(dates))
    
    # 초기 설정
    current_asset_values = initial_cash * weights
    asset_values[0] = current_asset_values
    portfolio_value[0] = initial_cash
    
    for i in range(1, len(dates)):
        prev_date = dates[i-1]
        curr_date = dates[i]
        
        # 1. 일별 수익률 반영
        current_asset_values = current_asset_values * (1 + pct_change.iloc[i].values)
        
        # 2. 적립식 입금 체크 (적립식 선택 시)
        if investment_type == "적립식" and contribution_amount > 0:
            is_contribution_day = False
            
            if contribution_freq == "매월" and curr_date.month != prev_date.month:
                is_contribution_day = True
            elif contribution_freq == "매분기" and (curr_date.month - 1) // 3 != (prev_date.month - 1) // 3:
                is_contribution_day = True
            elif contribution_freq == "매년" and curr_date.year != prev_date.year:
                is_contribution_day = True
                
            if is_contribution_day:
                # 입금액을 기존 포트폴리오 비중대로 나누어 투입
                curr_tot = np.sum(current_asset_values)
                if curr_tot > 0:
                    current_weights = current_asset_values / curr_tot
                else:
                    current_weights = weights
                current_asset_values += contribution_amount * current_weights
        
        # 3. 리밸런싱 조건 체크
        need_rebalance = False
        
        if strategy == "정적 (주기적)":
            if period == "매월" and curr_date.month != prev_date.month:
                need_rebalance = True
            elif period == "매분기" and (curr_date.month - 1) // 3 != (prev_date.month - 1) // 3:
                need_rebalance = True
            elif period == "매년" and curr_date.year != prev_date.year:
                need_rebalance = True
                
        elif strategy == "동적 (임계값 기반)":
            total_val = np.sum(current_asset_values)
            if total_val > 0:
                current_weights = current_asset_values / total_val
                weight_diff = np.abs(current_weights - weights)
                if np.any(weight_diff >= threshold):
                    need_rebalance = True
                    
        # 4. 리밸런싱 실행
        if need_rebalance:
            total_val = np.sum(current_asset_values)
            current_asset_values = total_val * weights
            
        asset_values[i] = current_asset_values
        portfolio_value[i] = np.sum(current_asset_values)
        
    portfolio_series = pd.Series(portfolio_value, index=dates)
    return portfolio_series

def get_performance_metrics(portfolio_series, risk_free_rate=0.035):
    """
    CAGR, MDD, Volatility, Sharpe Ratio 계산
    """
    total_days = (portfolio_series.index[-1] - portfolio_series.index[0]).days
    total_return = (portfolio_series.iloc[-1] / portfolio_series.iloc[0]) - 1
    
    if total_days > 0:
        cagr = ((portfolio_series.iloc[-1] / portfolio_series.iloc[0]) ** (365 / total_days)) - 1
    else:
        cagr = 0.0
        
    daily_returns = portfolio_series.pct_change().dropna()
    ann_vol = daily_returns.std() * np.sqrt(252)
    
    sharpe = (cagr - risk_free_rate) / ann_vol if ann_vol != 0 else 0
    
    cum_max = portfolio_series.cummax()
    drawdown = (portfolio_series - cum_max) / cum_max
    mdd = drawdown.min()
    
    return {
        "최종 평가금액": f"{portfolio_series.iloc[-1]:,.0f} 원",
        "누적 수익률": f"{total_return * 100:.2f}%",
        "CAGR (연평균 수익률)": f"{cagr * 100:.2f}%",
        "변동성 (연화)": f"{ann_vol * 100:.2f}%",
        "Sharpe Ratio": f"{sharpe:.2f}",
        "MDD (최대 낙폭)": f"{mdd * 100:.2f}%"
    }, drawdown

# ==========================================
# 2. 사이드바 UI
# ==========================================
st.sidebar.title("⚙️ 백테스트 설정")

# 기능 선택
menu = st.sidebar.radio(
    "원하는 기능을 선택하세요",
    ["1. 다중 종목 상대 수익률 비교", "2. 포트폴리오 자산배분 백테스트"]
)

st.sidebar.markdown("---")

# 공통 날짜 설정
start_date = st.sidebar.date_input("시작일", datetime.date(2020, 1, 1))
end_date = st.sidebar.date_input("종료일", datetime.date.today())

if menu == "1. 다중 종목 상대 수익률 비교":
    st.sidebar.subheader("📌 종목 입력")
    tickers_input = st.sidebar.text_input(
        "종목/티커 (쉼표 구분, 최대 10개)", 
        "삼성전자, AAPL, NVDA, S&P500"
    )

elif menu == "2. 포트폴리오 자산배분 백테스트":
    st.sidebar.subheader("📌 자산 및 비중 설정")
    tickers_input = st.sidebar.text_input("자산 목록 (쉼표 구분)", "SPY, TLT, GLD")
    weights_input = st.sidebar.text_input("자산별 비중 (합계 1.0, 쉼표 구분)", "0.5, 0.4, 0.1")
    
    st.sidebar.markdown("---")
    st.sidebar.subheader("💰 투자금 설정")
    investment_type = st.sidebar.selectbox("투자 방식", ["거치식", "적립식"])
    
    initial_cash = st.sidebar.number_input("최초 설정 금액 (원)", value=10000000, step=1000000, format="%d")
    
    contribution_amount = 0
    contribution_freq = "매월"
    if investment_type == "적립식":
        contribution_amount = st.sidebar.number_input("적립 금액 (원)", value=500000, step=100000, format="%d")
        contribution_freq = st.sidebar.selectbox("적립 주기", ["매월", "매분기", "매년"])
        
    st.sidebar.markdown("---")
    st.sidebar.subheader("⚖️ 리밸런싱 기준 설정")
    rebal_strategy = st.sidebar.selectbox("리밸런싱 전략", ["정적 (주기적)", "동적 (임계값 기반)"])
    
    rebal_period = "매월"
    rebal_threshold = 0.05
    if rebal_strategy == "정적 (주기적)":
        rebal_period = st.sidebar.selectbox("리밸런싱 주기", ["매월", "매분기", "매년"])
    else:
        rebal_threshold = st.sidebar.slider("임계값 (예: 0.05 = 5% 이탈 시)", 0.01, 0.20, 0.05, 0.01)

st.sidebar.markdown("---")
run_btn = st.sidebar.button("🚀 선택한 기능 실행하기", use_container_width=True)

# ==========================================
# 3. 메인 화면 동작
# ==========================================
st.title("📊 통합 포트폴리오 분석 대시보드")

if run_btn:
    raw_tickers = [t.strip() for t in tickers_input.split(",") if t.strip()]
    resolved_tickers = [resolve_ticker(t) for t in raw_tickers]
    
    if not resolved_tickers:
        st.error("올바른 종목/티커를 입력해주세요.")
        st.stop()
        
    with st.spinner("금융 데이터를 불러오는 중..."):
        try:
            data = yf.download(resolved_tickers, start=start_date, end=end_date)['Adj Close']
            if isinstance(data, pd.Series):
                data = data.to_frame()
            data = data.dropna()
        except Exception as e:
            st.error(f"데이터 다운로드 중 오류 발생: {e}")
            st.stop()

    if data.empty:
        st.warning("선택한 기간 또는 종목에 해당하는 데이터가 없습니다.")
        st.stop()

    # --------------------------------------
    # 기능 1: 다중 종목 상대 수익률 비교
    # --------------------------------------
    if menu == "1. 다중 종목 상대 수익률 비교":
        st.subheader("📈 다중 종목 상대 수익률 비교 ($100 기준 지수화)")
        
        normalized_df = (data / data.iloc[0]) * 100
        
        fig, ax = plt.subplots(figsize=(10, 5))
        for col in normalized_df.columns:
            ax.plot(normalized_df.index, normalized_df[col], label=col)
        ax.axhline(100, color='gray', linestyle='--', linewidth=0.8)
        ax.set_ylabel("지수화 가격 ($100 기준)")
        ax.legend()
        ax.grid(True, alpha=0.3)
        st.pyplot(fig)
        
        st.subheader("📋 기간별 요약")
        summary_df = pd.DataFrame({
            "시작가": data.iloc[0],
            "최종가": data.iloc[-1],
            "총 수익률(%)": ((data.iloc[-1] / data.iloc[0]) - 1) * 100
        })
        st.dataframe(summary_df.style.format({"시작가": "{:,.2f}", "최종가": "{:,.2f}", "총 수익률(%)": "{:+.2f}%"}))

    # --------------------------------------
    # 기능 2: 포트폴리오 자산배분 백테스트
    # --------------------------------------
    elif menu == "2. 포트폴리오 자산배분 백테스트":
        st.subheader("💼 자산배분 포트폴리오 성과 분석")
        
        try:
            weights = np.array([float(w.strip()) for w in weights_input.split(",") if w.strip()])
        except ValueError:
            st.error("비중은 숫자로 입력해주세요.")
            st.stop()
            
        if len(weights) != len(resolved_tickers):
            st.error("입력한 자산 수와 비중 개수가 일치하지 않습니다.")
            st.stop()
            
        if not np.isclose(np.sum(weights), 1.0):
            st.warning(f"비중 합계가 {np.sum(weights):.2f}입니다. 자동 표준화(합계 1.0)하여 계산합니다.")
            weights = weights / np.sum(weights)

        # 포트폴리오 가치 계산
        portfolio_series = calculate_rebalanced_portfolio(
            df=data,
            weights=weights,
            strategy=rebal_strategy,
            period=rebal_period,
            threshold=rebal_threshold,
            initial_cash=initial_cash,
            investment_type=investment_type,
            contribution_amount=contribution_amount,
            contribution_freq=contribution_freq
        )
        
        metrics, drawdown = get_performance_metrics(portfolio_series)
        
        # 성과 지표 출력 (4개 컬럼)
        m_cols = st.columns(3)
        keys = list(metrics.keys())
        for idx, key in enumerate(keys):
            m_cols[idx % 3].metric(label=key, value=metrics[key])
            
        # 포트폴리오 가치 변화 차트
        st.subheader("📈 포트폴리오 자산 추이")
        fig, ax = plt.subplots(figsize=(10, 4))
        ax.plot(portfolio_series.index, portfolio_series, label="Portfolio Value", color="blue")
        ax.set_ylabel("자산 가치 (원)")
        ax.grid(True, alpha=0.3)
        ax.legend()
        st.pyplot(fig)
        
        # Drawdown 차트
        st.subheader("📉 Drawdown (낙폭 차트)")
        fig_dd, ax_dd = plt.subplots(figsize=(10, 3))
        ax_dd.plot(drawdown.index, drawdown * 100, color="red", label="Drawdown (%)")
        ax_dd.fill_between(drawdown.index, drawdown * 100, 0, color="red", alpha=0.2)
        ax_dd.set_ylabel("낙폭 (%)")
        ax_dd.grid(True, alpha=0.3)
        ax_dd.legend()
        st.pyplot(fig_dd)

else:
    st.info("👈 왼쪽 사이드바에서 원하는 조건과 투자금을 설정한 후 **'🚀 선택한 기능 실행하기'** 버튼을 눌러주세요.")
