import streamlit as st
import yfinance as yf
import matplotlib.pyplot as plt
import datetime

# 1. 웹페이지 기본 설정
st.set_page_config(page_title="주가 비교 대시보드", layout="wide")

st.title("📈 애플 vs 마이크로소프트 주가 비교")
st.markdown("원하는 시작 날짜와 종료 날짜를 선택하면 실시간으로 Yahoo Finance에서 데이터를 가져와 그래프를 그립니다.")

# 2. 사이드바에 날짜 입력창 만들기
st.sidebar.header("조회 조건 설정")

# 기본 날짜 설정 (시작일: 2026년 1월 1일, 종료일: 오늘)
default_start = datetime.date(2026, 1, 1)
default_end = datetime.date.today()

# 유저가 캘린더에서 날짜 선택
start_date = st.sidebar.date_input("시작 날짜", default_start)
end_date = st.sidebar.date_input("종료 날짜", default_end)

# 안전장치: 시작 날짜가 종료 날짜보다 뒤에 있으면 경고 출력
if start_date > end_date:
    st.error("시작 날짜는 종료 날짜보다 앞서야 합니다.")
else:
    # 3. 데이터 가져오기 버튼
    if st.sidebar.button("주가 데이터 조회하기"):
        with st.spinner("데이터를 불러오는 중입니다..."):
            try:
                tickers = ["AAPL", "MSFT"]
                # 유저가 선택한 날짜 범위를 yfinance에 전달
                data = yf.download(tickers, start=start_date, end=end_date)["Close"]
                
                if not data.empty:
                    # 4. 그래프 그리기 영역
                    fig, ax = plt.subplots(figsize=(12, 6))
                    plt.style.use('seaborn-v0_8-whitegrid')
                    
                    # 데이터 시각화
                    ax.plot(data.index, data['AAPL'], label='Apple (AAPL)', color='#E67E22', linewidth=2)
                    ax.plot(data.index, data['MSFT'], label='Microsoft (MSFT)', color='#3498DB', linewidth=2)
                    
                    ax.set_title(f'Stock Price Comparison ({start_date} to {end_date})', fontsize=16, fontweight='bold', pad=15)
                    ax.set_xlabel('Date', fontsize=12)
                    ax.set_ylabel('Price (USD)', fontsize=12)
                    ax.legend(fontsize=11)
                    
                    # 5. 코랩의 plt.show() 대신 Streamlit 전용 함수로 그래프 출력!
                    st.pyplot(fig)
                    
                    # 최근 데이터 테이블도 보너스로 출력
                    st.subheader("최근 주가 데이터 목록")
                    st.dataframe(data.tail(10))
                else:
                    st.warning("해당 기간의 주가 데이터가 존재하지 않습니다.")
                    
            except Exception as e:
                st.error(f"데이터를 가져오는 중 오류가 발생했습니다: {e}")
