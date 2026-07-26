import streamlit as st
import yfinance as yf
import matplotlib.pyplot as plt
import datetime

# 1. 웹페이지 기본 설정
st.set_page_config(page_title="멀티 자산 주가 비교 대시보드", layout="wide")

st.title("📊 포트폴리오 다중 종목 주가 비교")
st.markdown("최대 5개 종목을 입력하고 기간을 선택하세요. 조회 가능한 정확한 주가만 추려 그래프와 요약 카드로 보여줍니다.")

# 2. 사이드바 조회 조건 설정
st.sidebar.header("🔍 조회 조건 설정")

# [기능 추가 1] 동적으로 5개 종목 입력받기 (기본값 제공)
st.sidebar.subheader("종목 티커 입력 (최대 5개)")
t1 = st.sidebar.text_input("종목 1", "AAPL").strip().upper()
t2 = st.sidebar.text_input("종목 2", "MSFT").strip().upper()
t3 = st.sidebar.text_input("종목 3", "005930.KS").strip().upper()  # 삼성전자
t4 = st.sidebar.text_input("종목 4", "379800.KS").strip().upper()  # KODEX 미국S&P500
t5 = st.sidebar.text_input("종목 5", "").strip().upper()            # 선택사항

# 입력된 티커 중 빈칸 제거 및 중복 제거
user_tickers = list(dict.fromkeys([t for t in [t1, t2, t3, t4, t5] if t]))

# 날짜 설정
default_start = datetime.date(2026, 1, 1)
default_end = datetime.date.today()
start_date = st.sidebar.date_input("시작 날짜", default_start)
end_date = st.sidebar.date_input("종료 날짜", default_end)

# 안전장치: 날짜 및 입력값 검증
if start_date > end_date:
    st.error("시작 날짜는 종료 날짜보다 앞서야 합니다.")
elif not user_tickers:
    st.warning("최소 한 개 이상의 종목 티커를 입력해 주세요.")
else:
    # 3. 데이터 가져오기 버튼
    if st.sidebar.button("주가 데이터 조회하기"):
        with st.spinner("Yahoo Finance에서 데이터를 검증하고 불러오는 중입니다..."):
            try:
                # [기능 추가 2 & 에러 방지] 전체 다운로드 후 유효한 열(Column)만 추출
                df_all = yf.download(user_tickers, start=start_date, end=end_date)["Close"]
                
                # 데이터가 단일 종목일 경우 Series 형태이므로 DataFrame으로 변환
                if isinstance(df_all, pd.Series):
                    df_all = df_all.to_frame(name=user_tickers[0])

                # 전체가 날아간 열(데이터 없는 엉터리 티커) 제거
                valid_df = df_all.dropna(how='all', axis=1)
                
                # 입력된 종목 중 제외된 종목 찾아내기
                valid_tickers = list(valid_df.columns)
                invalid_tickers = [t for t in user_tickers if t not in valid_tickers]
                
                if invalid_tickers:
                    st.toast(f"⚠️ 조회 불가 티커 제외됨: {', '.join(invalid_tickers)}", icon="⚠️")
                    st.sidebar.warning(f"제외된 종목: {', '.join(invalid_tickers)}")

                if not valid_df.empty and len(valid_tickers) > 0:
                    # 4. 그래프 그리기 영역
                    fig, ax = plt.subplots(figsize=(12, 6))
                    plt.style.use('seaborn-v0_8-whitegrid')
                    
                    for tk in valid_tickers:
                        # 각 종목의 데이터 추출
                        series_data = valid_df[tk].dropna()
                        ax.plot(series_data.index, series_data.values, label=tk, linewidth=2)
                    
                    ax.set_title(f'Stock Price Comparison ({start_date} ~ {end_date})', fontsize=16, fontweight='bold', pad=15)
                    ax.set_xlabel('Date', fontsize=12)
                    ax.set_ylabel('Price', fontsize=12)
                    ax.legend(fontsize=11)
                    
                    st.pyplot(fig)
                    
                    # [기능 추가 3] 종목별 최신 가격 요약 카드 (에러 완벽 방지)
                    st.subheader("📌 종목별 최신 가격 요약")
                    cols = st.columns(len(valid_tickers))
                    
                    for idx, tk in enumerate(valid_tickers):
                        # 안전하게 가장 최근 유효 종가 파이썬 float로 단일 추출
                        last_price = float(valid_df[tk].dropna().iloc[-1])
                        
                        # 원화/달러 구분 서식
                        if ".KS" in tk or ".RQ" in tk:
                            price_str = f"{int(last_price):,}원"
                        else:
                            price_str = f"${last_price:,.2f}"
                            
                        cols[idx].metric(label=tk, value=price_str)
                    
                    # 하단 데이터 테이블
                    st.subheader("최근 주가 데이터 목록")
                    st.dataframe(valid_df.tail(10))
                    
                else:
                    st.error("해당 조건으로 조회 가능한 주가 데이터가 없습니다. 티커를 다시 확인해 주세요.")
                    
            except Exception as e:
                st.error(f"데이터 처리 중 오류가 발생했습니다: {e}")
