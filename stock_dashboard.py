import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
from deep_translator import GoogleTranslator
import time
import requests
import xml.etree.ElementTree as ET
import urllib.parse
import json
import streamlit.components.v1 as components
try:
    import google.generativeai as genai
    HAS_GEMINI = True
except ImportError:
    HAS_GEMINI = False

# 페이지 기본 설정
st.set_page_config(page_title="금융 시장 데일리 리포트", layout="wide", initial_sidebar_state="collapsed")

# 토스(Toss) 스타일의 Custom CSS 적용
st.markdown("""
    <style>
    @import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.css');
    
    * { font-family: 'Pretendard', sans-serif; }
    
    .main { background-color: #ffffff; }
    
    /* 카카오 스타일 요약 카드 */
    .summary-card {
        background-color: white;
        border-radius: 12px;
        padding: 20px;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.05);
        margin-bottom: 20px;
        transition: all 0.3s ease;
        border: 1px solid #f0f0f0;
    }
    .summary-card:hover {
        transform: translateY(-5px);
        box-shadow: 0 10px 20px rgba(0, 0, 0, 0.06);
    }
    
    .metric-label { color: #888888; font-size: 14px; font-weight: 500; }
    .metric-value { color: #191919; font-size: 24px; font-weight: 700; margin-top: 5px; }
    .delta-up { color: #e65f5f; font-size: 14px; font-weight: 600; }
    .delta-down { color: #4376e6; font-size: 14px; font-weight: 600; }
    
    /* 종목 아이템 카드 스타일 */
    .stock-item-card-wrapper {
        background-color: white;
        border-radius: 12px;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.05);
        margin-bottom: 20px; /* 카드 간 간격 */
        transition: all 0.3s ease;
        overflow: hidden; /* 내부 요소의 border-radius 적용을 위해 */
        border: 1px solid #f0f0f0;
        display: flex;
        flex-direction: column;
    }
    .stock-item-card-wrapper:hover {
        transform: translateY(-5px);
        box-shadow: 0 10px 20px rgba(0, 0, 0, 0.06);
        border: 1px solid #FEE500; /* 마우스 오버 시 카카오 옐로우 테두리 */
    }

    /* 버튼 스타일 */
    .stButton>button {
        border-radius: 12px;
        background-color: #FEE500;
        color: #191919;
        border: none;
        padding: 0 15px;
        height: 65px;
        transition: 0.3s;
        font-weight: 700;
        font-size: 22px;
        text-align: left;
        justify-content: flex-start;
        display: flex;
        align-items: center;
        width: 100%;
    }
    .stButton>button:hover {
        color: #191919 !important;
        filter: brightness(1.1); /* 회색으로 변하지 않고 살짝 밝아짐 */
        background-color: #FEE500;
    }
    .stButton>button:active, .stButton>button:focus {
        color: #191919 !important;
        background-color: #FEE500 !important;
    }
    
    /* 뉴스 센티먼트 배지 */
    .badge-pos { background-color: #fff9c4; color: #191919; padding: 4px 8px; border-radius: 6px; font-size: 12px; font-weight: 600; }
    .badge-neg { background-color: #fce4ec; color: #e65f5f; padding: 4px 8px; border-radius: 6px; font-size: 12px; font-weight: 600; }

    </style>
    """, unsafe_allow_html=True)

@st.cache_data(ttl=600) # 10분간 캐시 유지
def fetch_market_data():
    """주요 시장 지표 및 나스닥 Top 10 데이터를 수집합니다."""
    tickers = {
        "나스닥100": "^NDX",
        "비트코인": "BTC-USD",
        "금": "GC=F",
        "VIX지수": "^VIX",
        "달러/원": "KRW=X",
        "미10년물 국채": "^TNX",
        "AI/반도체": "SOXX",
        "양자컴퓨터": "QTUM"
    }
    
    data = {}
    for name, symbol in tickers.items():
        ticker = yf.Ticker(symbol)
        # 데이터 안정성을 위해 15m가 없으면 1h로 시도
        hist = ticker.history(period="2d", interval="15m")
        if hist.empty: hist = ticker.history(period="5d", interval="60m")
        
        # 상대 수익률 비교 차트를 위한 1개월 일간 데이터 수집
        hist_1mo = ticker.history(period="1mo", interval="1d")
        
        if len(hist) >= 2:
            current_price = hist['Close'].iloc[-1]
            prev_price = hist['Close'].iloc[0]
            delta = current_price - prev_price
            delta_pct = (delta / prev_price) * 100
            data[name] = {
                "symbol": symbol,
                "price": current_price,
                "delta": delta,
                "delta_pct": delta_pct,
                "sparkline": hist['Close'],
                "hist_1mo": hist_1mo['Close'] if not hist_1mo.empty else None
            }
            
    # 나스닥 Top 10 종목 정보
    top_10_symbols = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AVGO", "PEP", "COST"]
    top_10_data = []
    for sym in top_10_symbols:
        t = yf.Ticker(sym)
        h = t.history(period="2d", interval="15m")
        if h.empty: h = t.history(period="5d", interval="60m")
        
        if len(h) >= 2:
            p_price = h['Close'].iloc[0]
            top_10_data.append({
                "symbol": sym,
                "price": h['Close'].iloc[-1],
                "delta_pct": ((h['Close'].iloc[-1] - p_price) / p_price) * 100,
                "sparkline": h['Close']
            })
            
    return data, top_10_data

def get_asset_history(symbol, period="1mo"):
    """특정 자산의 히스토리 데이터를 가져옵니다."""
    ticker = yf.Ticker(symbol)
    return ticker.history(period=period)

@st.cache_data(ttl=600) # 10분간 뉴스 데이터 캐싱
def process_news(symbol):
    """뉴스를 수집하고 번역 및 감성 분류를 수행합니다."""
    # 1. 검색어 최적화 (지수 기호 및 외환은 한글 키워드로 검색 품질 향상)
    news_map = {
        "^NDX": "나스닥 100",
        "^VIX": "VIX 공포지수",
        "^TNX": "미국 국채 금리",
        "KRW=X": "원달러 환율",
        "GC=F": "금 시세 전망",
        "BTC-USD": "비트코인 시황"
    }
    search_query = news_map.get(symbol, f"{symbol} 주식")
    
    # 2. 구글 뉴스 RSS 호출 (한국어/한국 지역 설정으로 즉시 뉴스 수집)
    encoded_query = urllib.parse.quote(search_query)
    url = f"https://news.google.com/rss/search?q={encoded_query}&hl=ko&gl=KR&ceid=KR:ko"
    
    try:
        response = requests.get(url, timeout=10)
        root = ET.fromstring(response.content)
        items = root.findall('.//item')
    except Exception:
        return []

    if not items: return []
    
    processed_news = []
    # 3. 감성 분석 키워드 (한글 뉴스 대응)
    pos_keywords = ['상승', '호재', '성장', '매수', '돌파', '긍정', '강세', '최고', '급등', '실적호조', '상회', '증가', '반등', '수혜']
    neg_keywords = ['하락', '악재', '우려', '매도', '폭락', '부정', '약세', '실망', '급락', '위기', '하회', '감소', '둔화', '쇼크', '손실']
    
    for item in items:
        title = item.find('title').text
        link = item.find('link').text
        source = item.find('source').text if item.find('source') is not None else "금융뉴스"
        pub_date = item.find('pubDate').text if item.find('pubDate') is not None else ""
        
        # 날짜 포맷팅 (GMT -> 한국 시간 보정 +9시간)
        try:
            dt = datetime.strptime(pub_date, '%a, %d %b %Y %H:%M:%S %Z')
            dt_kor = dt + timedelta(hours=9)
            formatted_date = dt_kor.strftime('%m-%d %H:%M')
        except:
            formatted_date = pub_date
            
        sentiment = "neutral"
        title_lower = title.lower()
        if any(word in title_lower for word in neg_keywords):
            sentiment = "negative"
        elif any(word in title_lower for word in pos_keywords):
            sentiment = "positive"
            
        processed_news.append({
            "title": title,
            "link": link,
            "sentiment": sentiment,
            "publisher": source,
            "date": formatted_date
        })
        
        if len(processed_news) >= 10:
            break
            
    return processed_news

def summarize_news_ai(news_list):
    """
    Google Gemini API를 사용하여 뉴스 목록을 핵심 한 문장으로 요약합니다.
    """
    if not news_list:
        return "요약할 뉴스가 없습니다."

    if not HAS_GEMINI:
        return "Google Generative AI 패키지가 설치되지 않았습니다. (pip install google-generativeai)"

    # 1. tqqq.md 컨텍스트 로드 (분석적 요약을 위해)
    context_report = ""
    try:
        with open(r"c:\Work\tqqq.md", "r", encoding="utf-8") as f:
            context_report = f.read()[:1000] # 분석 품질 향상을 위해 컨텍스트 확장
    except:
        pass

    news_context = "\n".join([f"- {n['title']}" for n in news_list])
    prompt = f"""당신은 전문 금융 분석가입니다. 다음 뉴스 헤드라인들을 종합하여 현재 시장 상황을 한국어 한 문장으로 요약하세요.
특히 아래의 TQQQ 관련 투자 보고서의 핵심 지표(변동성 잠식, 레버리지 구조 등)를 참고하여, 
현재 뉴스가 기술주 및 레버리지 투자자들에게 미칠 영향을 중심으로 통찰력 있게 분석하세요.

[참고 보고서 내용]:
{context_report}

[최신 뉴스 헤드라인]:
{news_context}

핵심 요약(한국어):"""

    # API 키 설정
    api_key = None
    try:
        api_key = st.secrets.get("GOOGLE_API_KEY")
    except:
        pass
    api_key = api_key or 'AIzaSyAQLjOYVrC63zg_qv-GvBlYtoYu6UBWw9A'

    try:
        genai.configure(api_key=api_key)
        # 404 오류(모델 미지원)를 해결하기 위해 시도 가능한 모델 목록을 순차적으로 호출합니다.
        # gemini-1.5-flash-latest -> gemini-1.5-flash -> gemini-pro (1.0 안정 버전)
        available_models = ['gemini-1.5-flash-latest', 'gemini-1.5-flash', 'gemini-pro']
        last_exception = ""

        for model_name in available_models:
            try:
                model = genai.GenerativeModel(model_name)
                response = model.generate_content(prompt)
                return f"**[Gemini 요약 ({model_name})]** {response.text}"
            except Exception as e:
                last_exception = str(e)
                continue
        
        return f"Gemini 요약 실패 (모든 모델 시도 결과): {last_exception}"
    except Exception as e:
        return f"Gemini 요약 중 오류 발생 (라이브러리 업데이트 권장: pip install -U google-generativeai): {str(e)}"

# 세션 상태 초기화
if 'selected_asset' not in st.session_state:
    st.session_state.selected_asset = "나스닥100"
if 'selected_symbol' not in st.session_state:
    st.session_state.selected_symbol = "^NDX"
# 상단 헤더 및 갱신 버튼
col_h1, col_h2 = st.columns([6, 1])
with col_h1:
    st.title("📈 금융 시장 데일리 리포트")
with col_h2:
    st.write("<div style='height: 12px;'></div>", unsafe_allow_html=True)
    if st.button("🔄 갱신", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    st.markdown(f'<p style="text-align: right; color: #8b95a1; font-size: 0.8rem; margin: 0;">마지막 업데이트: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>', unsafe_allow_html=True)

# 데이터 로드
with st.spinner("최신 시장 데이터를 불러오는 중..."):
    market_metrics, top_10 = fetch_market_data()

st.markdown("### 📊 시장 현황")
summary_cols = st.columns(3)

# 자연어 요약 생성 logic
vix = market_metrics['VIX지수']
ndx = market_metrics['나스닥100']
btc = market_metrics['비트코인']
vix_status = "공포(불안)" if vix['price'] > 20 else "안정"
market_trend = "상승세" if ndx['delta_pct'] > 0 else "하강세"
btc_trend = "강세" if btc['delta_pct'] > 0 else "약세"

def get_delta_html(delta_pct):
    color = "#e65f5f" if delta_pct >= 0 else "#4376e6"
    arrow = "▲" if delta_pct >= 0 else "▼"
    return f'<span style="color: {color}; font-size: 14px; font-weight: 600;">{arrow} {abs(delta_pct):.2f}%</span>'

with summary_cols[0]:
    st.markdown(f"""
    <div class="summary-card">
        <div style="flex-grow: 1;">
            <p class="metric-label">오늘의 시황</p>
            <p style="font-size:14px; color:#191919; line-height:1.6; margin-top:10px;">
                전일 글로벌 증시는 나스닥 기술주들의 {market_trend} 속에 혼조세를 보였으나, 
                VIX 지수가 {vix['price']:.2f}로 {vix_status} 지지력을 확인하며 시장의 회복 탄력성을 테스트하고 있습니다. 
                비트코인 역시 {btc['price']:,.0f}달러 부근에서 {btc_trend}를 나타내며 위험 자산 선호 심리를 자극하고 있습니다.
            </p>
        </div>
        <div style="margin-top: 20px; padding-top: 15px; border-top: 1px solid #f0f0f0;">
            <div style="display: flex; justify-content: space-between; margin-bottom: 5px;">
                <span style="font-size: 14px; font-weight: 600;">나스닥100</span> <span>{ndx['price']:,.2f} {get_delta_html(ndx['delta_pct'])}</span>
            </div>
            <div style="display: flex; justify-content: space-between; margin-bottom: 5px;">
                <span style="font-size: 14px; font-weight: 600;">비트코인</span> <span>{btc['price']:,.0f} {get_delta_html(btc['delta_pct'])}</span>
            </div>
            <div style="display: flex; justify-content: space-between;">
                <span style="font-size: 14px; font-weight: 600;">VIX 지수</span> <span>{vix['price']:.2f} {get_delta_html(vix['delta_pct'])}</span>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

with summary_cols[1]:
    tnx = market_metrics['미10년물 국채']
    usd = market_metrics['달러/원']
    gold = market_metrics['금']
    tnx_trend = "상승하며 긴축 압력을 가하고" if tnx['delta_pct'] > 0 else "하락하며 안정세를 보이고"
    usd_trend = "상승하며 원화 약세를 자극하고" if usd['delta_pct'] > 0 else "안정화되는"

    st.markdown(f"""
    <div class="summary-card">
        <div style="flex-grow: 1;">
            <p class="metric-label">매크로 지표</p>
            <p style="font-size:14px; color:#191919; line-height:1.6; margin-top:10px;">
                미 국채 10년물 금리가 {tnx['price']:.2f}% 수준으로 {tnx_trend} 있으며, 
                달러/원 환율은 {usd['price']:,.1f}원에서 {usd_trend} 양상을 보이고 있습니다. 
                안전자산인 국제 금 시세는 {gold['price']:,.1f}달러선에서 추이를 형성하며 글로벌 매크로 불확실성을 반영 중입니다.
            </p>
        </div>
        <div style="margin-top: 20px; padding-top: 15px; border-top: 1px solid #f0f0f0;">
            <div style="display: flex; justify-content: space-between; margin-bottom: 5px;">
                <span style="font-size: 14px; font-weight: 600;">미 10년 금리</span> <span>{tnx['price']:.2f}% {get_delta_html(tnx['delta_pct'])}</span>
            </div>
            <div style="display: flex; justify-content: space-between; margin-bottom: 5px;">
                <span style="font-size: 14px; font-weight: 600;">달러/원</span> <span>{usd['price']:,.1f}원 {get_delta_html(usd['delta_pct'])}</span>
            </div>
            <div style="display: flex; justify-content: space-between;">
                <span style="font-size: 14px; font-weight: 600;">금 시세</span> <span>${gold['price']:,.1f} {get_delta_html(gold['delta_pct'])}</span>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

with summary_cols[2]:
    # 섹터별 대표 수익률 계산 (사용자 요청 티커 기준)
    ai_perf = market_metrics.get("AI/반도체", {}).get("delta_pct", 0)
    quantum_perf = market_metrics.get("양자컴퓨터", {}).get("delta_pct", 0)
    ev_perf = next((s['delta_pct'] for s in top_10 if s['symbol'] == 'TSLA'), 0)

    # 섹터별 동적 요약 생성
    semi_desc = "상승하며 주도권을 유지하고" if ai_perf > 0 else "조정을 받으며 숨고르기에 들어간"
    quantum_desc = "긍정적인 흐름을" if quantum_perf > 0 else "신중한 움직임을"
    tsla_desc = "반등을 시도하는" if ev_perf > 0 else "압력을 받고 있는"

    st.markdown(f"""
    <div class="summary-card">
        <div style="flex-grow: 1;">
            <p class="metric-label" title="나스닥 100의 장기 성장을 견인하는 핵심 기술 혁신 분야">관심 섹터 ℹ️</p>
            <p style="font-size:14px; color:#191919; line-height:1.6; margin-top:10px;">
                반도체 섹터(SOXX)는 현재 {semi_desc} 모습이며, 양자컴퓨터(QTUM)는 시장에서 {quantum_desc} 나타내고 있습니다.
                테슬라(TSLA)를 포함한 전기차 섹터는 전반적으로 {tsla_desc} 상황입니다.
            </p>
        </div>
        <div style="margin-top: 20px; padding-top: 15px; border-top: 1px solid #f0f0f0;">
            <div style="display: flex; justify-content: space-between; margin-bottom: 5px;">
                <span style="font-size: 13px; font-weight: 600;">SOXX</span> <span>{get_delta_html(ai_perf)}</span>
            </div>
            <div style="display: flex; justify-content: space-between; margin-bottom: 5px;">
                <span style="font-size: 13px; font-weight: 600;">QTUM</span> <span>{get_delta_html(quantum_perf)}</span>
            </div>
            <div style="display: flex; justify-content: space-between;">
                <span style="font-size: 13px; font-weight: 600;">TSLA</span> <span>{get_delta_html(ev_perf)}</span>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

# FRED 데이터 시뮬레이션 (API 키 이슈 방지)
months = pd.date_range(end=datetime.now(), periods=24, freq='ME')
fed_rates = [0.25]*6 + [1.5]*6 + [3.5]*6 + [5.33]*6 # 시뮬레이션 데이터
cpi_data = [7.5, 8.2, 9.1, 8.5, 7.7, 6.5, 6.0, 5.0, 4.0, 3.2, 3.1, 3.4]*2

col_macro_left, col_macro_right = st.columns(2)

with col_macro_left:
    fig_macro = go.Figure()
    fig_macro.add_trace(go.Scatter(x=months, y=fed_rates, name="기준금리 (%)", line=dict(color='#4376e6', width=3)))
    fig_macro.add_trace(go.Scatter(x=months, y=cpi_data, name="CPI 물가 (YoY %)", line=dict(color='#e65f5f', width=3, dash='dot')))
    fig_macro.update_layout(
        height=350, margin=dict(l=20, r=20, t=20, b=20),
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    st.plotly_chart(fig_macro, use_container_width=True)

with col_macro_right:
    fig_comp = go.Figure()
    compare_assets = [("나스닥100", "#4376e6"), ("비트코인", "#f39c12"), ("금", "#f1c40f")]
    
    for asset_name, color in compare_assets:
        if asset_name in market_metrics and market_metrics[asset_name].get('hist_1mo') is not None:
            series = market_metrics[asset_name]['hist_1mo']
            # 수익률 정규화 (첫 번째 데이터 포인트를 0%로 설정)
            normalized_perf = ((series / series.iloc[0]) - 1) * 100
            fig_comp.add_trace(go.Scatter(
                x=series.index, # 날짜 기준으로 정렬
                y=normalized_perf,
                name=asset_name,
                line=dict(color=color, width=2.5)
            ))
            
    fig_comp.update_layout(
        height=350, margin=dict(l=20, r=20, t=20, b=20),
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        yaxis=dict(ticksuffix="%", gridcolor="#f0f0f0"),
        xaxis=dict(visible=True, gridcolor="#f0f0f0", tickformat="%m-%d")
    )
    st.plotly_chart(fig_comp, use_container_width=True)

st.divider()
st.markdown("### 📈 종목 현황")

# 1. 데이터 리스트 통합 (Row 1: 주요 자산 5개 + Row 2~3: 나스닥 Top 10)
row1_names = ["나스닥100", "비트코인", "금", "VIX지수", "달러/원"]
combined_items = []

for name in row1_names:
    if name in market_metrics:
        item = market_metrics[name].copy()
        item['label'] = name
        combined_items.append(item)

for stock in top_10:
    item = stock.copy()
    item['label'] = stock['symbol']
    combined_items.append(item)

# 2. 3x5 그리드 렌더링
for r in range(3):
    cols = st.columns(5)
    for c in range(5):
        idx = r * 5 + c
        if idx < len(combined_items):
            item = combined_items[idx]
            with cols[c]:
                # 1. 카드 래퍼 시작
                st.markdown('<div class="stock-item-card-wrapper">', unsafe_allow_html=True)
                
                # 2. 파이썬 로직: 변동률에 따른 색상 결정
                btn_color = "#e65f5f" if item['delta_pct'] >= 0 else "#4376e6"
                
                # 3. 개별 버튼 배경색 주입
                st.markdown(f"""
                    <style>
                    div[data-testid="column"]:nth-of-type({c+1}) button {{
                        background-color: {btn_color} !important;
                        color: white !important;
                        border-radius: 0 !important;
                    }}
                    div[data-testid="column"]:nth-of-type({c+1}) button:hover {{
                        background-color: {btn_color} !important;
                        color: white !important;
                    }}
                    </style>
                """, unsafe_allow_html=True)
                
                # 4. 상단 영역: 종목 버튼
                if st.button(f"{item['label']}", key=f"btn_grid_{idx}", use_container_width=True):
                    st.session_state.selected_asset = item['label']
                    st.session_state.selected_symbol = item['symbol']
                    st.rerun()

                # 5. 하단 영역: 좌우 영역 구분 (좌: 차트, 우: 정보)
                grid_bottom_col1, grid_bottom_col2 = st.columns([6, 4])
                
                with grid_bottom_col1:
                    # 좌측: 전일 차트 (Sparkline)
                    line_color = "#e65f5f" if item['delta_pct'] >= 0 else "#4376e6"
                    fig_spark = go.Figure(data=go.Scatter(y=item['sparkline'], line=dict(color=line_color, width=2)))
                    fig_spark.update_layout(
                        height=55, margin=dict(l=15, r=0, t=5, b=5),
                        xaxis=dict(visible=False), yaxis=dict(visible=False),
                        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                        showlegend=False,
                        hovermode=False
                    )
                    st.plotly_chart(fig_spark, use_container_width=True, config={'displayModeBar': False, 'staticPlot': True})

                with grid_bottom_col2:
                    # 우측: 현재가 및 변동률 정보
                    color_class = "delta-up" if item['delta_pct'] >= 0 else "delta-down"
                    arrow = "▲" if item['delta_pct'] >= 0 else "▼"
                    st.markdown(f"""
                    <div style="padding: 10px; padding-right: 15px; text-align:right; margin-bottom:0; background-color: #ffffff; border-top: 1px solid #f0f0f0;">
                        <p class="metric-value" style="font-size:15px; margin:0;">{item['price']:,.2f}</p>
                        <p class="{color_class}" style="font-size:12px; margin:0;">{arrow} {abs(item['delta_pct']):.2f}%</p>
                    </div>
                    """, unsafe_allow_html=True)
                
                # 6. 카드 래퍼 종료
                st.markdown("</div>", unsafe_allow_html=True)

st.divider()
st.markdown(f"### 🔍 {st.session_state.selected_asset} ({st.session_state.selected_symbol}) 상세 분석")
col_left, col_right = st.columns([2, 1]) # 우측 실시간 뉴스 가로 사이즈 약 33% (1/3)

with col_left:
    # 선택한 종목의 Ticker 객체 생성 및 데이터 수집
    ticker_obj = yf.Ticker(st.session_state.selected_symbol)
    full_hist = ticker_obj.history(period="1y")
    # 야후 파이낸스 공식 52주 최고가(year_high) 정보를 우선적으로 가져옵니다.
    # 데이터가 없을 경우에 대비해 히스토리 데이터의 최댓값을 백업으로 사용합니다.
    high_52w = ticker_obj.fast_info.get('year_high') or full_hist['High'].max()
    
    # 1. 좌측 상단: 차트 (최근 1개월/22영업일 분량 표시)
    hist_data = full_hist.tail(22)
    fig_detail = go.Figure(data=[go.Candlestick(x=hist_data.index,
                    open=hist_data['Open'], high=hist_data['High'],
                    low=hist_data['Low'], close=hist_data['Close'],
                    increasing_line_color='#e65f5f', decreasing_line_color='#4376e6')])
    fig_detail.update_layout(height=450, margin=dict(l=0, r=0, t=0, b=0), xaxis_rangeslider_visible=False)
    st.plotly_chart(fig_detail, use_container_width=True)
    
    # 2. 좌측 하단: 최근 가격 히스토리
    st.markdown("##### 일별 가격 변동")
    # 변동폭, 변동률 및 Gap(52주 고점 대비 차이) 계산
    df_calc = full_hist.copy()
    df_calc['Change'] = df_calc['Close'].diff()
    df_calc['Change(%)'] = df_calc['Close'].pct_change() * 100
    df_calc['Gap'] = high_52w - df_calc['Close']
    df_calc['Gap(%)'] = (df_calc['Gap'] / high_52w) * 100
    
    # 최근 10일(약 2주 영업일) 데이터 추출 및 포맷팅
    display_df = df_calc.tail(10).sort_index(ascending=False).reset_index()
    display_df['Date'] = display_df['Date'].dt.strftime('%Y-%m-%d')
    
    # 플러스/마이너스에 따른 색상 및 볼드 스타일 적용 함수
    def color_delta(val):
        color = '#e65f5f' if val > 0 else '#4376e6' if val < 0 else '#191919'
        return f'color: {color}; font-weight: bold;'

    # 요청된 컬럼 순서로 구성하여 출력
    st.dataframe(
        display_df[['Date', 'Close', 'Change', 'Change(%)', 'Gap', 'Gap(%)']].style.format({
            'Close': '{:,.2f}',
            'Change': '{:,.2f}',
            'Change(%)': '{:,.2f}%',
            'Gap': '{:,.2f}',
            'Gap(%)': '{:,.2f}%'
        }).map(color_delta, subset=['Change', 'Change(%)']), 
        use_container_width=True,
        hide_index=True
    )

with col_right:
    # 3. 우측: 최신 뉴스 및 요약 버튼
    col_n1, col_n2 = st.columns([3, 1])
    with col_n1:
        st.markdown("##### 최신 뉴스")
    with col_n2:
        btn_copy = st.button("📋 복사", key="news_copy_btn", use_container_width=True)

    news_list = process_news(st.session_state.selected_symbol)

    # 복사 버튼 클릭 시 현재 선택된 종목의 뉴스 링크 목록을 클립보드에 복사
    if btn_copy:
        if news_list:
            # 현재 선택된 종목의 뉴스 링크들만 추출하여 텍스트 생성
            copy_text = "\n".join([n['link'] for n in news_list])
            
            # JavaScript를 통한 클립보드 복사 실행
            js_code = f"navigator.clipboard.writeText({json.dumps(copy_text)});"
            components.html(f"<script>{js_code}</script>", height=0)
            
            # 사용자 피드백 표시 (선택된 종목명 명시)
            st.success(f"**{st.session_state.selected_asset}** 뉴스 링크 {len(news_list)}건이 복사되었습니다!")
            with st.expander("복사된 내용 확인", expanded=True):
                st.code(copy_text, language="text")
        else:
            st.warning("복사할 뉴스 링크가 없습니다.")

    if not news_list:
        st.info("현재 해당 종목에 대한 최신 뉴스가 없습니다.")
    else:
        for news in news_list:
            # 감성 배지 설정
            if news['sentiment'] == "positive":
                badge = '<span class="badge-pos">🟢 긍정</span>'
            elif news['sentiment'] == "negative":
                badge = '<span class="badge-neg">🔴 부정</span>'
            else:
                badge = '<span style="background-color: #eee; color: #666; padding: 4px 8px; border-radius: 6px; font-size: 11px; font-weight: 600;">⚪ 중립</span>'

            st.markdown(f"""
            <div style="border-bottom:1px solid #eee; padding:10px 0;">
                <p style="font-size:12px; color:#8b95a1; margin-bottom:5px;">{news['publisher']} - {news['date']} | {badge}</p>
                <a href="{news['link']}" target="_blank" style="text-decoration:none; color:#191f28; font-weight:600; font-size:14px;">{news['title']}</a>
            </div>
            """, unsafe_allow_html=True)

st.divider()