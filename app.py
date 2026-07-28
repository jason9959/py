import streamlit as st
import yfinance as yf
import matplotlib.pyplot as plt
import datetime
import re
import pandas as pd

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

# ==========================================
# [사이드바] 메인 모드 선택
# ==========================================
st.sidebar.title("📌 대시보드 메뉴")
app_mode = st.sidebar.selectbox(
    "실행할 기능을 선택하세요:",
    ["1. 다중 종목 상대 수익률 비교 (기준 100)", "2. 신규 기능 (개발 예정 모드)"]
)

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
    
    # ------------------------------------------
    # 👉 [위치 변경] 버튼을 비교종목 입력 텍스트 위로 이동
    # ------------------------------------------
    run_button = st.sidebar.button("🚀 주가 데이터 조회 및 비교하기", use_container_width=True)

    st.sidebar.markdown("---")

    # [STEP 2] 종목 1~10 순서 입력 수집
    st.sidebar.subheader("📈 비교 종목 입력 (최대 10개)")
    
    default_inputs = ["AAPL", "MSFT", "005930.KS", "379800.KS", "", "", "", "", "", ""]
    
    # 순서를 명확하게 보존하기 위해 구조화된 데이터(List of Dict) 생성
    input_stock_list = []

    for i in range(10):
        slot_label = f"종목 {i+1}"
        val = st.sidebar.text_input(
            slot_label, 
            value=default_inputs[i], 
            key=f"stock_input_{i+1}",
            placeholder="티커 또는 한글 종목명"
        )
        
        resolved_t = resolve_ticker(val)
        if resolved_t:
            input_stock_list.append({
                "slot": slot_label,       # 예: "종목 1"
                "raw_input": val,          # 예: "AAPL"
                "ticker": resolved_t      # 예: "AAPL"
            })

    # [STEP 3] 유효성 검사 및 중복 처리 (사용자 입력 순서 유지)
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
    if start_date > end_date:
        st.error("시작 날짜는 종료 날짜보다 앞서야 합니다.")
    elif not ordered_target_tickers:
        st.warning("최소 1개 이상의 올바른 종목을 입력해 주세요.")
    else:
        # 버튼클릭 상태 판단
        if run_button:
            with st.spinner("Yahoo Finance에서 실시간 데이터를 불러오는 중..."):
                try:
                    # 1) 전체 종목 데이터 수집
                    df_raw = yf.download(ordered_target_tickers, start=start_date, end=end_date)["Close"]
                    
                    # 단일 종목 예외 처리
                    if isinstance(df_raw, pd.Series):
                        df_raw = df_raw.to_frame(name=ordered_target_tickers[0])

                    # 2) yf.download의 알파벳 정렬을 무효화하고 사용자 입력 순서로 강제 고정
                    existing_in_order = [t for t in ordered_target_tickers if t in df_raw.columns]
                    df_ordered = df_raw[existing_in_order]

                    # 3) 공통 거래일 필터링 (결측치 제거)
                    common_df = df_ordered.dropna()

                    if not common_df.empty and len(common_df) > 0:
                        final_tickers = list(common_df.columns)
                        base_date = common_df.index[0].strftime('%Y-%m-%d')
                        
                        # 4) 첫 거래일 기준 100 지수화
                        indexed_df = (common_df / common_df.iloc[0]) * 100

                        # --------------------------------------
                        # 5) 시각화: 그래프 출력
                        # --------------------------------------
                        st.subheader(f"📈 상대 성과 추이 그래프 (공통 기준일: {base_date} = 100)")
                        
                        fig, ax = plt.subplots(figsize=(12, 6))
                        plt.style.use('seaborn-v0_8-whitegrid')
                        
                        # 기준선(100) 표시
                        ax.axhline(100, color='gray', linestyle='--', linewidth=1.2, alpha=0.7, label="Base (100)")
                        
                        # 순서 보장된 final_tickers로 라인 그리기
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
                        
                        # --------------------------------------
                        # 6) 요약 카드 및 데이터 테이블
                        # --------------------------------------
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
                        st.error("입력하신 종목들의 공통 거래일 주가 데이터가 존재하지 않습니다. 날짜 범위를 조정해 보세요.")
                except Exception as e:
                    st.error(f"데이터 처리 중 오류가 발생했습니다: {e}")

# ==========================================
# 기능 2: 신규 기능 모드
# elif app_mode == "2. 신규 기능 (개발 예정 모드)":
#     st.title("🧮 새로운 기능 전용 페이지")
#     st.info("이곳은 두 번째 메뉴 선택 시 사용할 추가 기능 페이지입니다.")
# ==========================================



# ==========================================
# 기능 2: 포트폴리오 자산배분 백테스트 및 성과 분석
# ==========================================
elif app_mode == "2. 신규 기능 (개발 예정 모드)":
    st.title("💼 포트폴리오 자산배분 백테스트 & 위험 분석")
    st.markdown("설정한 자산 비중에 따른 **포트폴리오 총자산 성장 추이**와 **CAGR, MDD, 샤프 지수** 등 핵심 투자 지표를 분석합니다.")

    st.sidebar.header("🔍 백테스트 조건 설정")

    # [STEP 1] 날짜 및 초기 투자금 설정
    st.sidebar.subheader("📅 기간 및 초기 자금")
    default_start = datetime.date(2021, 1, 1)
    default_end = datetime.date.today()
    start_date = st.sidebar.date_input("2-1. 시작 날짜", default_start, key="bt_start")
    end_date = st.sidebar.date_input("2-2. 종료 날짜", default_end, key="bt_end")
    
    init_balance = st.sidebar.number_input("2-3. 초기 투자금 ($ 또는 원)", value=10000, step=1000)

    st.sidebar.markdown("---")

    # [STEP 2] 종목 및 비중 입력
    st.sidebar.subheader("⚖️ 포트폴리오 자산 비중 (%)")
    st.sidebar.caption("비중의 합이 100%가 되도록 설정하세요.")

    bt_default_inputs = ["AAPL", "MSFT", "QQQ", "SCHD", "005930.KS"]
    bt_default_weights = [30, 20, 20, 20, 10]

    input_portfolio = []
    
    for i in range(5):
        col_t, col_w = st.sidebar.columns([2, 1])
        with col_t:
            val = st.text_input(f"종목 {i+1}", value=bt_default_inputs[i] if i < len(bt_default_inputs) else "", key=f"bt_tk_{i+1}")
        with col_w:
            weight = st.number_input(f"비중%", value=bt_default_weights[i] if i < len(bt_default_weights) else 0, min_value=0, max_value=100, step=5, key=f"bt_wt_{i+1}")
        
        resolved_t = resolve_ticker(val)
        if resolved_t and weight > 0:
            input_portfolio.append({
                "ticker": resolved_t,
                "weight": weight
            })

    total_weight = sum([item["weight"] for item in input_portfolio])
    
    st.sidebar.markdown(f"**현재 총 비중 합계:** `{total_weight}%`")
    if total_weight != 100:
        st.sidebar.warning("⚠️ 비중 합계가 100%가 되도록 조정해 주세요.")

    st.sidebar.markdown("---")
    run_bt_button = st.sidebar.button("📊 백테스트 실행하기", use_container_width=True)

    # ==========================================
    # [STEP 3] 백테스트 연산 및 데이터 처리
    # ==========================================
    if run_bt_button:
        if start_date >= end_date:
            st.error("시작 날짜는 종료 날짜보다 앞서야 합니다.")
        elif not input_portfolio:
            st.warning("최소 1개 이상의 유효한 종목과 0% 초과의 비중을 입력해 주세요.")
        elif total_weight != 100:
            st.error(f"비중 합계가 {total_weight}%입니다. 100%가 되도록 변경 후 실행해 주세요.")
        else:
            with st.spinner("과거 주가 데이터수집 및 포트폴리오 백테스팅 중..."):
                try:
                    bt_tickers = [item["ticker"] for item in input_portfolio]
                    weights = [item["weight"] / 100.0 for item in input_portfolio]

                    # 1) 데이터 수집
                    df_raw = yf.download(bt_tickers, start=start_date, end=end_date)["Close"]

                    if isinstance(df_raw, pd.Series):
                        df_raw = df_raw.to_frame(name=bt_tickers[0])

                    # 입력 순서 및 공통 거래일 처리
                    existing_tickers = [t for t in bt_tickers if t in df_raw.columns]
                    df_clean = df_raw[existing_tickers].dropna()

                    if df_clean.empty or len(df_clean) < 2:
                        st.error("해당 기간의 공통 거래일 데이터가 부족합니다.")
                    else:
                        # 2) 일별 수익률 산출
                        daily_returns = df_clean.pct_change().dropna()
                        
                        # 3) 가중합을 통한 포트폴리오 일별 수익률 계산
                        portfolio_daily_return = (daily_returns * weights).sum(axis=1)

                        # 4) 자산 누적 성과 계산 (Cumulative Returns)
                        portfolio_cum_return = (1 + portfolio_daily_return).cumprod()
                        portfolio_val = init_balance * portfolio_cum_return

                        # 5) 주요 지표 산출 (CAGR, Volatility, Sharpe, MDD)
                        total_days = (df_clean.index[-1] - df_clean.index[0]).days
                        years = total_days / 365.25
                        
                        final_val = portfolio_val.iloc[-1]
                        total_return_pct = ((final_val / init_balance) - 1) * 100
                        cagr = (((final_val / init_balance) ** (1 / years)) - 1) * 100 if years > 0 else 0

                        # 변동성 및 샤프 지수 (무위험 수익률 2% 가정)
                        volatility = portfolio_daily_return.std() * (252 ** 0.5) * 100
                        risk_free_rate = 0.02
                        mean_annual_return = portfolio_daily_return.mean() * 252
                        sharpe_ratio = (mean_annual_return - risk_free_rate) / (volatility / 100) if volatility != 0 else 0

                        # MDD (Maximum Drawdown)
                        peak = portfolio_val.cummax()
                        drawdown = (portfolio_val - peak) / peak
                        mdd = drawdown.min() * 100

                        # --------------------------------------
                        # 6) 결과 시각화
                        # --------------------------------------
                        st.subheader("📌 핵심 성과 지표 (Key Metrics)")
                        m1, m2, m3, m4, m5 = st.columns(5)
                        
                        m1.metric("최종 자산 평가액", f"{final_val:,.0f}")
                        m2.metric("총 수익률", f"{total_return_pct:+.2f}%")
                        m3.metric("CAGR (연평균 성장률)", f"{cagr:.2f}%")
                        m4.metric("MDD (최대 낙폭)", f"{mdd:.2f}%")
                        m5.metric("Sharpe Ratio", f"{sharpe_ratio:.2f}")

                        st.markdown("---")

                        # 차트 1: 자산 가치 상승 곡선
                        st.subheader("📈 포트폴리오 자산 성장 추이")
                        fig_pf, ax_pf = plt.subplots(figsize=(12, 5))
                        plt.style.use('seaborn-v0_8-whitegrid')

                        ax_pf.plot(portfolio_val.index, portfolio_val, label="Portfolio Value", color="#1f77b4", linewidth=2.5)
                        ax_pf.set_title(f'Portfolio Growth ({df_clean.index[0].strftime("%Y-%m-%d")} ~ {df_clean.index[-1].strftime("%Y-%m-%d")})', fontsize=14, fontweight='bold')
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

