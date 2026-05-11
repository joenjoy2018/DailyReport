import yfinance as yf
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from datetime import datetime
from deep_translator import GoogleTranslator
from fredapi import Fred

st.set_page_config(page_title="Daily Report", page_icon="📈", layout="wide")
st.title("Daily Report")

# 관심종목 카드 스타일(회색 배경 및 테두리) 설정을 위한 CSS 주입
st.markdown("""
    <style>
    /* 토스 스타일 폰트 및 배경색 */
    @import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.css');
    
    html, body, [class*="css"] {
        font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, system-ui, Roboto, sans-serif !important;
    }

    .stApp {
        background-color: #f2f4f6;
    }

    /* 메인 컨테이너 패딩 조절 */
    .main .block-container {
        padding-top: 3rem;
        padding-bottom: 5rem;
        max-width: 1100px;
    }

    /* 토스풍 카드 스타일 */
    [data-testid="column"] {
        background-color: #ffffff !important;
        padding: 20px !important;
        border-radius: 28px !important;
        border: 1px solid #eff1f3 !important; /* 경계선을 명확히 하기 위해 연한 테두리 추가 */
        box-shadow: 0 8px 16px rgba(0,0,0,0.02) !important;
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
        margin-bottom: 16px;
    }

    [data-testid="column"]:hover {
        transform: translateY(-4px);
        box-shadow: 0 12px 24px rgba(0,0,0,0.08) !important;
    }

    /* 버튼 스타일 (토스 블루) */
    .stButton > button {
        border-radius: 14px !important;
        padding: 10px 20px !important;
        font-weight: 600 !important;
        border: none !important;
        font-size: 1.1rem !important; /* 종목명 글씨 크기 확대 */
    }
    
    .stButton > button[kind="primary"] {
        background-color: #3182f6 !important;
        color: white !important;
    }
    
    .stButton > button[kind="secondary"] {
        background-color: #e8f3ff !important;
        color: #3182f6 !important;
    }

    /* 메인 리포트 텍스트 스타일 */
    .report-text {
        color: #4e5968 !important;
        line-height: 1.6;
        font-size: 1.05rem;
        background: white;
        padding: 10px 20px;
        border-radius: 16px;
        margin-bottom: 12px;
    }

    @media (max-width: 1000px) {
        [data-testid="stHorizontalBlock"] {
            flex-wrap: wrap !important;
        }
        [data-testid="column"] {
            min-width: 220px !important; /* 카드가 최소 220px 공간을 확보하면 옆으로 배치 */
            flex: 1 1 220px !important;
        }
    }
    @media (max-width: 480px) {
        [data-testid="column"] {
            min-width: 100% !important; /* 모바일처럼 아주 좁은 화면에서만 1개씩 표시 */
        }
    }
    </style>
""", unsafe_allow_html=True)

# FRED API 설정 (키가 없는 경우 기능을 스킵하도록 처리)
# 보안을 위해 운영 환경에서는 st.secrets 등을 권장합니다.
FRED_API_KEY = "04e4aee612130db4f92a25611e5f198b"

@st.cache_data(show_spinner=False)
def get_fred_client(api_key):
    return Fred(api_key=api_key) if api_key else None

@st.cache_data(show_spinner=False)
def load_fred_macro(_fred_client):
    """FRED에서 주요 거시경제 지표 수집"""
    if not _fred_client:
        return None
    try:
        # FEDFUNDS (연방기금금리), UNRATE (실업률), CPIAUCSL (CPI)
        fed_series = _fred_client.get_series('FEDFUNDS')
        unrate_series = _fred_client.get_series('UNRATE')
        cpi_series = _fred_client.get_series('CPIAUCSL')
        
        # CPI YoY 시리즈 계산 (차트용)
        cpi_yoy_series = (cpi_series.pct_change(periods=12) * 100).dropna()
        
        # 최근 24개월 데이터프레임 생성 (시각화용)
        df_macro = pd.DataFrame({
            '금리': fed_series,
            '물가(YoY)': cpi_yoy_series,
            '실업률': unrate_series
        }).dropna().tail(24)
        
        return {
            "fed_funds": fed_series.iloc[-1],
            "fed_funds_prev": fed_series.iloc[-2],
            "unrate": unrate_series.iloc[-1],
            "unrate_prev": unrate_series.iloc[-2],
            "cpi_yoy": cpi_yoy_series.iloc[-1],
            "cpi_yoy_prev": cpi_yoy_series.iloc[-2],
            "df_macro": df_macro,
            "last_updated": cpi_series.index[-1].strftime('%Y-%m')
        }
    except Exception as e:
        st.sidebar.error(f"FRED 데이터 로드 실패: {e}")
        return None

# 세션 상태 초기화 (선택된 종목 관리)
if "selected_asset" not in st.session_state:
    st.session_state.selected_asset = "나스닥100"

ASSETS = {
    "나스닥100": "^NDX",
    "비트코인": "BTC-USD",
    "금": "GC=F",
    "VIX 지수": "^VIX",
    "달러/원": "KRW=X",
}
SECTORS = {
    "정보기술(IT)": "XLK",
    "금융": "XLF",
    "헬스케어": "XLV",
    "에너지": "XLE",
    "임의소비재": "XLY",
    "산업재": "XLI"
}
DEFAULT_ASSET = "나스닥100"

@st.cache_data(show_spinner=False)
def load_history(symbol: str, period: str, interval: str):
    hist = yf.Ticker(symbol).history(period=period, interval=interval)
    return hist

@st.cache_data(show_spinner=False)
def load_asset_info(symbol: str):
    ticker = yf.Ticker(symbol)
    
    try:
        # 최신 가격 및 변동 정보 추출
        hist = ticker.history(period="2d")
        if len(hist) >= 2:
            current_price = hist['Close'].iloc[-1]
            previous_close = hist['Close'].iloc[-2]
            volume = hist['Volume'].iloc[-1]
        else:
            current_price = ticker.info.get("regularMarketPrice") or ticker.info.get("currentPrice")
            previous_close = ticker.info.get("regularMarketPreviousClose")
            volume = ticker.info.get("regularMarketVolume")
    except Exception:
        current_price = None
        previous_close = None
        volume = None

    return {
        "symbol": symbol,
        "current_price": current_price,
        "previous_close": previous_close,
        "volume": volume,
    }


@st.cache_data(show_spinner=False)
def translate_title(text):
    """뉴스 타이틀을 한국어로 번역 (실패 시 원문 반합)"""
    if not text:
        return text
    try:
        return GoogleTranslator(source='auto', target='ko').translate(text)
    except Exception:
        return text

def analyze_sentiment(title):
    """제목의 키워드를 분석하여 긍정/부정 분류"""
    pos_keywords = ['상승', '호재', '성장', '돌파', '이익', '호조', '긍정', '급등', '매수', '강세', '낙관', '수익', '개선', '신고가']
    neg_keywords = ['하락', '악재', '둔화', '우려', '손실', '부정', '급락', '매도', '약세', '비관', '침체', '실망', '쇼크', '하회']
    
    score = sum(1 for word in pos_keywords if word in title)
    score -= sum(1 for word in neg_keywords if word in title)
    
    return "positive" if score >= 0 else "negative"

def format_price(value):
    if value is None:
        return "-"
    return f"{value:,.2f}"


def format_volume(value):
    if value is None:
        return "-"
    return f"{int(value):,}"


def format_change(current, previous):
    if current is None or previous is None:
        return None
    change = current - previous
    return change / previous * 100 if previous != 0 else None


def build_summary_line(name, pct):
    if pct is None:
        return f"- {name}: 데이터가 없습니다."
    if pct > 0.2:
        tone = "강세"
    elif pct < -0.2:
        tone = "약세"
    else:
        tone = "보합"
    return f"- {name}는 {tone}({pct:+.2f}%)를 보이고 있습니다."

selected_info = {name: load_asset_info(symbol) for name, symbol in ASSETS.items()}

# 리포트 데이터 수집 및 생성 로직 상단 이동
vix_info = selected_info["VIX 지수"]
tnx_info = load_asset_info("^TNX")

# FRED 매크로 데이터 로드
fred_client = get_fred_client(FRED_API_KEY)
macro_data = load_fred_macro(fred_client)
macro_desc = ""
if macro_data:
    # 금리 및 물가 추세 분석 문구 생성
    rate_trend = "유지되고" if macro_data['fed_funds'] == macro_data['fed_funds_prev'] else ("상승하며" if macro_data['fed_funds'] > macro_data['fed_funds_prev'] else "인하되며")
    cpi_trend = "둔화되는" if macro_data['cpi_yoy'] < macro_data['cpi_yoy_prev'] else "반등하는"
    
    macro_desc = f"미 연방기금금리는 {macro_data['fed_funds']:.2f}%로 {rate_trend} 있으며, 소비자물가(CPI)는 전년 대비 {macro_data['cpi_yoy']:.1f}% 기록하며 최근 {cpi_trend} 추세를 보이고 있습니다. 실업률은 {macro_data['unrate']:.1f}% 수준입니다. "

ndx_pct = format_change(selected_info["나스닥100"]["current_price"], selected_info["나스닥100"]["previous_close"])
btc_pct = format_change(selected_info["비트코인"]["current_price"], selected_info["비트코인"]["previous_close"])
gold_pct = format_change(selected_info["금"]["current_price"], selected_info["금"]["previous_close"])
krw_pct = format_change(selected_info["달러/원"]["current_price"], selected_info["달러/원"]["previous_close"])

market_news = []
try:
    news_objs = yf.Ticker("^GSPC").news
    if news_objs:
        # Yahoo Finance 뉴스 API 구조 변경에 따른 대응 (상단 리포트용)
        market_news = [item.get('title') or item.get('content', {}).get('title') for item in news_objs[:3]]
        market_news = [t for t in market_news if t]
        market_news = [translate_title(t) for t in market_news]
except:
    pass

vix_desc = f"VIX 지수는 {vix_info.get('current_price'):.2f}를 기록하며 " + ("시장 내 공포 심리가 다소 높은" if (vix_info.get('current_price') or 0) > 20 else "투자 심리가 비교적 안정적인") + " 구간에 머물러 있습니다" if vix_info.get('current_price') else ""
tnx_desc = f"미 10년물 국채금리는 {tnx_info.get('current_price'):.3f}% 수준으로, 이는 기술주를 포함한 위험 자산의 밸류에이션에 직접적인 영향을 미치는 핵심 지표로 작용하고 있습니다" if tnx_info.get('current_price') else ""
news_desc = f"최근 시장의 주요 화두로는 {', '.join(market_news)} 등이 거론되고 있습니다" if market_news else "현재 시장은 주요 경제 지표 발표를 앞두고 관망세가 짙은 모습입니다"

# 섹터 정보 수집 및 요약 생성
sector_changes = []
for s_name, s_symbol in SECTORS.items():
    s_info = load_asset_info(s_symbol)
    s_pct = format_change(s_info["current_price"], s_info["previous_close"])
    if s_pct is not None:
        sector_changes.append((s_name, s_pct))

sector_report_msg = ""
if sector_changes:
    # 상승률 기준 정렬
    sorted_sectors = sorted(sector_changes, key=lambda x: x[1], reverse=True)
    max_gain = sorted_sectors[0]
    max_loss = sorted_sectors[-1]
    sector_report_msg = f"섹터별로는 {max_gain[0]} 업종이 {max_gain[1]:+.2f}%로 가장 강세를 보이는 반면, {max_loss[0]} 업종은 {max_loss[1]:+.2f}%로 가장 큰 하락폭을 기록하고 있습니다."

query_date = datetime.now().strftime("%Y-%m-%d")

def get_tone(pct):
    if pct is None: return "데이터 없음"
    return "상승세" if pct > 0.2 else ("하락세" if pct < -0.2 else "보합세")

# 문맥에 맞게 단락 통합 및 텍스트 구성
report_header = f"{query_date} 글로벌 금융 시장 현황입니다."
report_body1 = f"{macro_desc}현재 {vix_desc} 있으며, {tnx_desc}."
report_body2 = f"종합적으로 볼 때 {news_desc}. 특히 나스닥 지수가 {ndx_pct:+.2f}%의 변동을 보이며 시장의 방향성을 주도하는 가운데, {sector_report_msg}"
report_body3 = f"관심 자산별 세부 동향을 살펴보면, 나스닥100 지수는 현재 **{get_tone(ndx_pct)}**({ndx_pct:+.2f}%)를 기록하며 시장의 기술주 중심 흐름을 반영하고 있습니다. " \
               f"가상자산 시장에서 비트코인은 {btc_pct:+.2f}% 변동하며 투자자들의 위험 선호 심리를 대변하고 있으며, " \
               f"안전 자산인 금({gold_pct:+.2f}%)과 달러/원 환율({krw_pct:+.2f}%)의 움직임은 글로벌 불확실성과 국내 수급 환경의 변화를 고스란히 보여주고 있습니다."

# 글씨 크기를 조절하여(#####) 상단에 표시
st.markdown(f"<h2 style='color: #191f28;'>{report_header}</h2>", unsafe_allow_html=True)
st.markdown(f"<div class='report-text'>{report_body1}</div>", unsafe_allow_html=True)
st.markdown(f"<div class='report-text'>{report_body2}</div>", unsafe_allow_html=True)
st.markdown(f"<div class='report-text'>{report_body3}</div>", unsafe_allow_html=True)

st.markdown("---")
st.markdown("<h3 style='color: #191f28; margin-bottom: 20px;'>📅 Market Events</h3>", unsafe_allow_html=True)
col_ev1, col_ev2 = st.columns(2)

with col_ev1:
    st.markdown("#### 📝 Review")
    st.write("지난 세션은 소비자물가지수(CPI) 둔화 소식에 따른 금리 인하 기대감이 시장을 주도했습니다. 특히 AI 관련 빅테크주들이 강세를 보이며 지수 상승을 견인했습니다.")
    st.write("• **CPI 지표 예상치 하회**로 위험자산 선호 심리 확산")
    st.write("• **엔비디아 등 주요 반도체 섹터** 신고가 경신 흐름")

with col_ev2:
    st.markdown("#### 🕒 Schedule")
    st.write("금일은 미 연준 위원들의 발언과 주간 고용 지표 발표가 예정되어 있습니다. 옵션 만기일을 앞둔 수급 변동성 확대에 유의할 필요가 있습니다.")
    st.write("• **연준 주요 인사 연설** (통화정책 힌트 주시)")
    st.write("• **주간 신규 실업수당 청구건수** 발표")

if macro_data is not None:
    st.markdown("---")
    st.markdown("<h3 style='color: #191f28; margin-bottom: 20px;'>📊 Macro Trends (Last 24M)</h3>", unsafe_allow_html=True)
    with st.container():
        macro_fig = go.Figure()
        # 금리 라인 (Toss Blue)
        macro_fig.add_trace(go.Scatter(x=macro_data['df_macro'].index, y=macro_data['df_macro']['금리'], 
                                      mode='lines+markers', name='연방기금금리', line=dict(color='#3182f6', width=3)))
        # 물가 라인 (Red)
        macro_fig.add_trace(go.Scatter(x=macro_data['df_macro'].index, y=macro_data['df_macro']['물가(YoY)'], 
                                      mode='lines+markers', name='물가상승률(YoY)', line=dict(color='#f04452', width=3)))
        
        macro_fig.update_layout(
            template="plotly_white",
            height=350,
            margin=dict(l=20, r=20, t=20, b=20),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            hovermode="x unified",
            xaxis=dict(showgrid=True, gridcolor='#f2f4f6'),
            yaxis=dict(showgrid=True, gridcolor='#f2f4f6')
        )
        st.plotly_chart(macro_fig, use_container_width=True, config={'displayModeBar': False})

st.markdown("---")

st.markdown("<h3 style='color: #191f28; margin-bottom: 20px;'>📊 Tickers</h3>", unsafe_allow_html=True)
card_cols = st.columns(len(ASSETS), gap="medium")
for col, (name, symbol) in zip(card_cols, ASSETS.items()):
    data = selected_info[name]
    price = data["current_price"]
    prev = data["previous_close"]
    pct = format_change(price, prev)

    with col:
        # 종목명 버튼: 선택 시 파란색(primary), 미선택 시 연한 파란색(secondary)
        is_selected = (st.session_state.selected_asset == name)
        if st.button(name, key=f"btn_{name}", use_container_width=True, type="primary" if is_selected else "secondary"):
            st.session_state.selected_asset = name
            st.rerun()

        # 가격 및 변동률 정보를 중앙 정렬된 HTML로 표시하여 카드 형태 완성
        if price is not None:
            color = "#f04452" if (pct or 0) > 0 else "#3182f6"
            pct_val = f"{pct:+.2f}%" if pct is not None else "-"
            st.markdown(f"""
                <div style="text-align: center; padding-top: 12px;">
                    <div style="font-size: 1.6rem; font-weight: 700; color: #191f28; letter-spacing: -0.5px;">{format_price(price)}</div>
                    <div style="font-size: 0.95rem; font-weight: 600; color: {color}; margin-top: 2px;">{pct_val}</div>
                </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown("<div style='text-align: center; padding-top: 12px; color: #adb5bd;'>-</div>", unsafe_allow_html=True)

st.markdown("---")

selected_asset = st.session_state.selected_asset
ticker = ASSETS[selected_asset]
period = "1mo"
interval = "1d"
show_candle = False

try:
    history = load_history(ticker, period, interval)
except Exception as exc:
    st.error(f"데이터를 불러오는 중 오류가 발생했습니다: {exc}")
    st.stop()

if history.empty:
    st.warning("데이터가 존재하지 않습니다. 심볼을 확인해주세요.")
else:
    # 차트와 최근 데이터를 가로로 배치 (약 2:1 비율)
    col_chart, col_data = st.columns([2, 1])

    # Y축 범위 계산 (최저/최고가 기준 10% 마진 추가)
    y_min_data = history["Low"].min() if show_candle else history["Close"].min()
    y_max_data = history["High"].max() if show_candle else history["Close"].max()
    price_range = y_max_data - y_min_data
    # 가격 변동이 없는 경우 대비
    margin = price_range * 0.1 if price_range > 0 else y_min_data * 0.01
    y_axis_range = [y_min_data - margin, y_max_data + margin]

    with col_chart:
        if show_candle:
            fig = go.Figure(
                data=[
                    go.Candlestick(
                        x=history.index,
                        open=history["Open"],
                        high=history["High"],
                        low=history["Low"],
                        close=history["Close"],
                        increasing_line_color="#00B050",
                        decreasing_line_color="#FF4C4C",
                    )
                ]
            )
        else:
            fig = go.Figure(
                data=[
                    go.Scatter(x=history.index, y=history["Close"], mode='lines+markers', name='종가', line=dict(color='#3182f6', width=3))
                ]
            )

        fig.update_layout(
            title=selected_asset,
            template="plotly_white",
            height=500,
            xaxis_rangeslider_visible=False,
            yaxis=dict(range=y_axis_range, tickformat=",.2f")
        )
        st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

    with col_data:
        # 전일 대비 변동 계산을 위해 원본 데이터에 diff 추가
        df_display = history.copy()
        df_display['diff'] = df_display['Close'].diff()
        df_display = df_display.sort_index(ascending=False)
        df_display.index = df_display.index.date

        def style_close_col(row):
            # 상승 시 빨간색(#f04452), 하락 시 파란색(#3182f6), 보합 시 기본색
            color = "#f04452" if row['diff'] > 0 else "#3182f6" if row['diff'] < 0 else "#191f28"
            # Close 컬럼에만 색상과 Bold 적용
            return [f'color: {color}; font-weight: bold' if col == 'Close' else '' for col in row.index]

        st.dataframe(
            df_display[["Open", "High", "Low", "Close", "diff"]].style
            .format("{:,.2f}", subset=["Open", "High", "Low", "Close", "diff"])
            .apply(style_close_col, axis=1),
            use_container_width=True, 
            height=505
        )

    st.markdown("---")
    # st.subheader(f"📰 {selected_asset} 최신 뉴스") # 요청에 따라 타이틀 삭제
    try:
        news_data = yf.Ticker(ticker).news
        if news_data:
            pos_items = []
            neg_items = []
            for item in news_data[:12]:
                title = item.get('title') or item.get('content', {}).get('title', '제목 없음')
                title = translate_title(title)
                link = item.get('link') or item.get('content', {}).get('canonicalUrl', {}).get('url', '#')
                publisher = item.get('publisher') or item.get('content', {}).get('provider', {}).get('displayName', '출처 미상')
                
                # 날짜 추출 및 형식화 (MM-DD)
                ts = item.get('providerPublishTime')
                date_str = datetime.fromtimestamp(ts).strftime('%m-%d') if ts else (item.get('content', {}).get('pubDate') or "0000-00-00")[5:10]
                
                # 요청하신 [날짜] 제목, (출처) 형식 구성
                news_entry = f"[{date_str}] [{title}]({link}), ({publisher})"
                
                if analyze_sentiment(title) == "positive":
                    pos_items.append(news_entry)
                else:
                    neg_items.append(news_entry)
            
            # 좌우 컬럼으로 배치
            col_pos_news, col_neg_news = st.columns(2)
            with col_pos_news:
                st.markdown("🟢 **긍정 / 중립 뉴스**")
                if pos_items: st.markdown("  \n".join(pos_items))
                else: st.write("분류된 뉴스가 없습니다.")
                
            with col_neg_news:
                st.markdown("🔴 **부정 뉴스**")
                if neg_items: st.markdown("  \n".join(neg_items))
                else: st.write("분류된 뉴스가 없습니다.")
        else:
            st.write("관련 뉴스가 없습니다.")
    except Exception as e:
        st.info(f"뉴스 데이터를 가져올 수 없습니다. ({e})")

st.markdown("---")
st.caption("데이터 제공: Yahoo Finance (yfinance)")
