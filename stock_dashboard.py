import yfinance as yf
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
import plotly.graph_objects as go
from datetime import datetime
from deep_translator import GoogleTranslator
from fredapi import Fred

st.set_page_config(page_title="Daily Report", page_icon="📈", layout="wide")

# --- UI Constants ---
TOSS_BLUE = "#3182f6"
TOSS_RED = "#f04452"
TOSS_GRAY_BG = "#f2f4f6"
TOSS_TEXT_MAIN = "#191f28"
TOSS_TEXT_SUB = "#4e5968"

col_title, col_refresh = st.columns([0.88, 0.12])
with col_title:
    st.title("Daily Report")
with col_refresh:
    st.markdown("<div style='padding-top: 2.5rem;'></div>", unsafe_allow_html=True)
    if st.button("🔄 갱신", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

st.markdown("""
    <style>
    @import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.css');
    
    html, body, [class*="css"] {
        font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, system-ui, Roboto, sans-serif !important;
    }

    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    div[data-testid="stToast"] {display: none;}
    div[data-testid="stStatusWidget"] {display: none;}

    .stApp { background-color: #f2f4f6; }

    .main .block-container {
        padding-top: 3rem;
        padding-bottom: 5rem;
        max-width: 1100px;
    }

    [data-testid="column"] {
        background-color: #ffffff !important;
        padding: 24px !important;
        border-radius: 24px !important;
        border: none !important;
        box-shadow: 0 4px 12px rgba(0,0,0,0.04) !important;
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
        margin-bottom: 24px;
    }

    [data-testid="column"]:hover {
        transform: translateY(-4px);
        box-shadow: 0 12px 24px rgba(0,0,0,0.08) !important;
    }

    .stButton > button {
        border-radius: 14px !important;
        padding: 10px 20px !important;
        border: none !important;
        font-size: 1.1rem !important;
        font-weight: 800 !important;
    }
    
    .stButton > button[kind="primary"] {
        background-color: #3182f6 !important;
        color: white !important;
        box-shadow: 0 4px 12px rgba(49, 130, 246, 0.3) !important;
    }
    
    .stButton > button[kind="secondary"] {
        background-color: #e8f3ff !important;
        color: #3182f6 !important;
    }

    .asset-card-content {
        text-align: center;
        margin-top: -15px;
        user-select: none;
    }
    .asset-price {
        font-size: 1.4rem;
        font-weight: 700;
        color: #191f28;
        margin-bottom: 4px;
    }
    .asset-change {
        font-size: 0.9rem;
        font-weight: 600;
    }

    .report-text {
        color: #4e5968 !important;
        line-height: 1.6;
        font-size: 1.05rem;
        background: white;
        padding: 10px 20px;
        border-radius: 16px;
        margin-bottom: 12px;
        user-select: text;
    }

    .event-title {
        font-size: 1.1rem;
        font-weight: 800;
        color: #191f28;
        margin-bottom: 12px;
        border-left: 5px solid #3182f6;
        padding-left: 12px;
    }
    .event-bullet { font-size: 0.95rem; color: #4e5968; margin-bottom: 8px; }
    .news-item { margin-bottom: 12px; }

    @media (max-width: 1000px) {
        [data-testid="stHorizontalBlock"] { flex-wrap: wrap !important; }
        [data-testid="column"] { min-width: 200px !important; flex: 1 1 200px !important; }
    }
    </style>
""", unsafe_allow_html=True)

# FRED API Key 안전하게 가져오기
try:
    FRED_API_KEY = st.secrets["FRED_API_KEY"]
except:
    # secrets.toml 파일이 없거나 키가 없는 경우 기본 키 사용
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
        
        df_macro = pd.DataFrame({
            '금리': fed_series,
            '물가(YoY)': cpi_yoy_series,
            '실업률': unrate_series
        }).dropna().tail(24)
        
        return {
            "fed_funds": fed_series.iloc[-1],
            "fed_funds_prev": fed_series.iloc[-2],
            "unrate": unrate_series.iloc[-1],
            "cpi_yoy": cpi_yoy_series.iloc[-1],
            "cpi_yoy_prev": cpi_yoy_series.iloc[-2],
            "df_macro": df_macro,
        }
    except Exception as e:
        # st.sidebar.error(f"FRED 데이터 로드 실패: {e}") # 사이드바가 숨겨져 있어 사용자에게 보이지 않으므로 제거
        return None

def render_asset_card(name, price, pct, is_top10=False):
    """공통 자산 카드 렌더링 헬퍼"""
    if price is None:
        st.markdown("<div class='asset-card-content'>-</div>", unsafe_allow_html=True)
        return
    
    color = TOSS_RED if (pct or 0) > 0 else TOSS_BLUE if (pct or 0) < 0 else TOSS_TEXT_MAIN
    price_str = format_price(price)
    pct_str = f"{pct:+.2f}%" if pct is not None else "-"
    
    margin_top = "-12px" if is_top10 else "-15px"
    st.markdown(f"""
        <div class="asset-card-content" style="margin-top: {margin_top}; margin-bottom: 10px;">
            <div class="asset-price">{price_str}</div>
            <div class="asset-change" style="color: {color};">{pct_str}</div>
        </div>
    """, unsafe_allow_html=True)

if "selected_asset" not in st.session_state:
    st.session_state.selected_asset = "나스닥100"

ASSETS = {"나스닥100": "^NDX", "비트코인": "BTC-USD", "금": "GC=F", "VIX 지수": "^VIX", "달러/원": "KRW=X"}
SECTORS = {"정보기술(IT)": "XLK", "금융": "XLF", "헬스케어": "XLV", "에너지": "XLE", "임의소비재": "XLY", "산업재": "XLI"}
NAS_TOP10 = ["AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "AVGO", "TSLA", "COST", "NFLX"]

@st.cache_data(show_spinner=False)
def load_history(symbol: str, period: str, interval: str):
    try:
        return yf.Ticker(symbol).history(period=period, interval=interval)
    except:
        return pd.DataFrame() # 데이터 로드 실패 시 빈 DataFrame 반환

@st.cache_data(show_spinner=False)
def load_asset_info(symbol: str):
    ticker = yf.Ticker(symbol)
    
    try:
        hist = ticker.history(period="5d") # 클라우드 환경에서 .info보다 .history가 더 안정적
        if not hist.empty:
            current_price = hist['Close'].iloc[-1]
            previous_close = hist['Close'].iloc[-2] if len(hist) >= 2 else current_price
            volume = hist['Volume'].iloc[-1]
        else:
            info = ticker.info
            current_price = info.get("regularMarketPrice") or info.get("currentPrice")
            previous_close = info.get("regularMarketPreviousClose")
            volume = info.get("regularMarketVolume")
    except:
        current_price, previous_close, volume = None, None, None

    return {"symbol": symbol, "current_price": current_price, "previous_close": previous_close, "volume": volume}

@st.cache_data(show_spinner=False)
def translate_title(text):
    if not text: return text
    try:
        return GoogleTranslator(source='auto', target='ko').translate(text)
    except:
        return text

def analyze_sentiment(title):
    pos = ['상승', '호재', '성장', '돌파', '이익', '호조', '긍정', '급등', '매수', '강세', '낙관', '수익', '개선', '신고가']
    neg = ['하락', '악재', '둔화', '우려', '손실', '부정', '급락', '매도', '약세', '비관', '침체', '실망', '쇼크', '하회']
    score = sum(1 for w in pos if w in title) - sum(1 for w in neg if w in title)
    return "positive" if score >= 0 else "negative"

def format_price(value):
    return f"{value:,.2f}" if value is not None else "-"


def format_volume(value):
    if value is None:
        return "-"
    return f"{int(value):,}"


def format_change(current, previous):
    if current is None or previous is None:
        return None
    change = current - previous
    return change / previous * 100 if previous != 0 else None

selected_info = {name: load_asset_info(symbol) for name, symbol in ASSETS.items()}
vix_info = selected_info["VIX 지수"]
tnx_info = load_asset_info("^TNX")

fred_client = get_fred_client(FRED_API_KEY)
macro_data = load_fred_macro(fred_client)
macro_desc = ""
if macro_data:
    # 금리 및 물가 추세 분석 문구 생성
    rate_trend = "유지되고" if macro_data['fed_funds'] == macro_data['fed_funds_prev'] else ("상승하고" if macro_data['fed_funds'] > macro_data['fed_funds_prev'] else "인하되고")
    cpi_trend = "둔화하는" if macro_data['cpi_yoy'] < macro_data['cpi_yoy_prev'] else "반등하는"
    
    macro_desc = f"미 연방기금금리는 {macro_data['fed_funds']:.2f}%로 {rate_trend} 있으며, 소비자물가(CPI)는 전년 대비 {macro_data['cpi_yoy']:.1f}% 기록하며 최근 {cpi_trend} 추세를 보이고 있습니다. 실업률은 {macro_data['unrate']:.1f}% 수준입니다. "

ndx_pct = format_change(selected_info["나스닥100"]["current_price"], selected_info["나스닥100"]["previous_close"])
btc_pct = format_change(selected_info["비트코인"]["current_price"], selected_info["비트코인"]["previous_close"])
gold_pct = format_change(selected_info["금"]["current_price"], selected_info["금"]["previous_close"])
krw_pct = format_change(selected_info["달러/원"]["current_price"], selected_info["달러/원"]["previous_close"])

market_news = []
try:
    news_objs = yf.Ticker("^GSPC").news
    if news_objs:
        market_news = [item.get('title') or item.get('content', {}).get('title') for item in news_objs[:3]]
        market_news = [t for t in market_news if t]
        market_news = [translate_title(t) for t in market_news]
except:
    pass

vix_desc = f"VIX 지수는 {vix_info.get('current_price'):.2f}를 기록하며 " + ("시장 내 공포 심리가 다소 높은" if (vix_info.get('current_price') or 0) > 20 else "투자 심리가 비교적 안정적인") + " 구간에 머물러 있습니다" if vix_info.get('current_price') else ""
tnx_desc = f"미 10년물 국채금리는 {tnx_info.get('current_price'):.3f}% 수준으로 자산 가치 평가의 핵심 지표로 작용하고 있습니다" if tnx_info.get('current_price') else ""
news_desc = f"시장의 주요 화두로는 {', '.join(market_news)} 등이 거론되고 있습니다" if market_news else "현재 시장은 주요 경제 지표 발표를 앞두고 관망세가 짙은 모습입니다"

sector_changes = []
for s_name, s_symbol in SECTORS.items():
    info = load_asset_info(s_symbol)
    s_pct = format_change(info["current_price"], info["previous_close"])
    if s_pct is not None:
        sector_changes.append((s_name, s_pct))

sector_report_msg = ""
if sector_changes:
    sorted_sectors = sorted(sector_changes, key=lambda x: x[1], reverse=True)
    max_gain = sorted_sectors[0]
    max_loss = sorted_sectors[-1]
    sector_report_msg = f"섹터별로는 {max_gain[0]} 업종이 {max_gain[1]:+.2f}%로 가장 강세를 보이는 반면, {max_loss[0]} 업종은 {max_loss[1]:+.2f}%로 가장 큰 하락폭을 기록하고 있습니다."

now = datetime.now()
days_ko = ["월", "화", "수", "목", "금", "토", "일"]
query_date = now.strftime("%Y-%m-%d") + f" ({days_ko[now.weekday()]})"

def get_tone(pct):
    if pct is None: return "데이터 없음"
    return "상승세" if pct > 0.2 else ("하락세" if pct < -0.2 else "보합세")

def safe_pct(pct):
    return f"{pct:+.2f}%" if pct is not None else "데이터 미수신"

n_pct_s, b_pct_s, g_pct_s, k_pct_s = safe_pct(ndx_pct), safe_pct(btc_pct), safe_pct(gold_pct), safe_pct(krw_pct)

report_header = f"{query_date} 글로벌 금융 시장 현황입니다."
report_body1 = f"{macro_desc}현재 {vix_desc} 있으며, {tnx_desc}."
report_body2 = f"종합적으로 볼 때 나스닥 지수가 {n_pct_s}의 변동을 보이며 시장의 방향성을 주도하는 가운데, {sector_report_msg}"
report_body3 = f"자산별로 나스닥100은 현재 <b>{get_tone(ndx_pct)}</b>({n_pct_s})를 기록 중입니다. " \
               f"비트코인은 {b_pct_s} 변동하며 투심을 대변하고 있으며, 금({g_pct_s})과 환율({k_pct_s})은 매크로 불확실성을 반영하고 있습니다. " \
               f"또한, {news_desc}."

st.markdown(f"<h3 style='color: {TOSS_TEXT_MAIN}; font-weight: 800;'>{report_header}</h3>", unsafe_allow_html=True)
st.markdown(f"<div class='report-text'>{report_body1}</div>", unsafe_allow_html=True)
st.markdown(f"<div class='report-text'>{report_body2}</div>", unsafe_allow_html=True)
st.markdown(f"<div class='report-text'>{report_body3}</div>", unsafe_allow_html=True)

st.markdown("---")
st.markdown(f"<h3 style='color: {TOSS_TEXT_MAIN}; font-weight: 800; margin-bottom: 20px;'>📅 Market Events</h3>", unsafe_allow_html=True)
col_ev1, col_ev2 = st.columns(2)
with col_ev1:
    st.markdown("<div class='event-title'>Review</div>", unsafe_allow_html=True)
    st.markdown(f"<div style='margin-bottom:12px; color: {TOSS_TEXT_SUB};'>소비자물가지수(CPI) 둔화 소식에 따른 금리 인하 기대감이 시장을 주도했습니다. 특히 기술주들이 강세를 보였습니다.</div>", unsafe_allow_html=True)
    st.markdown("<div class='event-bullet'>• <b>CPI 지표 예상치 하회</b>로 위험자산 선호 심리 확산</div>", unsafe_allow_html=True)
    st.markdown("<div class='event-bullet'>• <b>엔비디아 등 주요 반도체 섹터</b> 신고가 경신 흐름</div>", unsafe_allow_html=True)
with col_ev2:
    st.markdown("<div class='event-title'>Schedule</div>", unsafe_allow_html=True)
    st.markdown(f"<div style='margin-bottom:12px; color: {TOSS_TEXT_SUB};'>미 연준 위원들의 발언과 주간 고용 지표 발표가 예정되어 있습니다. 수급 변동성 확대에 유의할 필요가 있습니다.</div>", unsafe_allow_html=True)
    st.markdown("<div class='event-bullet'>• <b>연준 주요 인사 연설</b> (통화정책 힌트 주시)</div>", unsafe_allow_html=True)
    st.markdown("<div class='event-bullet'>• <b>주간 신규 실업수당 청구건수</b> 발표</div>", unsafe_allow_html=True)

if macro_data is not None:
    st.markdown("---")
    st.markdown(f"<h3 style='color: {TOSS_TEXT_MAIN}; font-weight: 800; margin-bottom: 20px;'>📊 Macro Trends (Last 24M)</h3>", unsafe_allow_html=True)
    macro_fig = go.Figure()
    macro_fig.add_trace(go.Scatter(x=macro_data['df_macro'].index, y=macro_data['df_macro']['금리'], mode='lines+markers', name='금리', line=dict(color=TOSS_BLUE, width=3)))
    macro_fig.add_trace(go.Scatter(x=macro_data['df_macro'].index, y=macro_data['df_macro']['물가(YoY)'], mode='lines+markers', name='물가(YoY)', line=dict(color=TOSS_RED, width=3)))
    macro_fig.update_layout(template="plotly_white", height=300, margin=dict(l=10, r=10, t=10, b=10), legend=dict(orientation="h", y=1.1, x=1, xanchor="right"), hovermode="x unified")
    st.plotly_chart(macro_fig, use_container_width=True, config={'displayModeBar': False})

st.markdown("---")
st.markdown(f"<h3 style='color: {TOSS_TEXT_MAIN}; font-weight: 800; margin-bottom: 20px;'>🏛️ Nasdaq Top 10 Summary</h3>", unsafe_allow_html=True)
for i in range(0, len(NAS_TOP10), 5):
    cols = st.columns(5)
    for j, sym in enumerate(NAS_TOP10[i:i+5]):
        info = load_asset_info(sym)
        pct = format_change(info["current_price"], info["previous_close"])
        is_sel = (st.session_state.selected_asset == sym)
        with cols[j]:
            if st.button(sym, key=f"nas_{sym}", use_container_width=True, type="primary" if is_sel else "secondary"):
                st.session_state.selected_asset = sym
                st.rerun()
            render_asset_card(sym, info["current_price"], pct, is_top10=True)

st.markdown("---")
st.markdown(f"<h3 style='color: {TOSS_TEXT_MAIN}; font-weight: 800; margin-bottom: 20px;'>📊 Market Summary</h3>", unsafe_allow_html=True)
card_cols = st.columns(len(ASSETS), gap="medium")
for col, (name, symbol) in zip(card_cols, ASSETS.items()):
    info = selected_info[name]
    pct = format_change(info["current_price"], info["previous_close"])
    with col:
        is_sel = (st.session_state.selected_asset == name)
        if st.button(name, key=f"btn_{name}", use_container_width=True, type="primary" if is_sel else "secondary"):
            st.session_state.selected_asset = name
            st.rerun()
        render_asset_card(name, info["current_price"], pct)

st.markdown("---")

selected_asset = st.session_state.selected_asset
ticker = ASSETS.get(selected_asset, selected_asset)
period = "1mo"
interval = "1d"

try:
    history = load_history(ticker, period, interval)
except Exception as exc:
    st.error(f"데이터를 불러오는 중 오류가 발생했습니다: {exc}")
    st.stop()

if history.empty:
    st.warning("데이터가 존재하지 않습니다. 심볼을 확인해주세요.")
else:
    col_chart, col_data = st.columns([2, 1])
    y_min, y_max = history["Close"].min(), history["Close"].max()
    margin = (y_max - y_min) * 0.1 if y_max != y_min else y_min * 0.01
    
    with col_chart:
        fig = go.Figure(data=[go.Scatter(x=history.index, y=history["Close"], mode='lines+markers', name='Close', line=dict(color=TOSS_BLUE, width=3))])
        fig.update_layout(
            title=dict(
                text=selected_asset, 
                x=0.5, 
                xanchor='center', 
                font=dict(size=22, family='Pretendard', color=TOSS_TEXT_MAIN, weight=800)
            ), 
            template="plotly_white", 
            height=500, 
            xaxis_rangeslider_visible=False, 
            yaxis=dict(range=[y_min - margin, y_max + margin], tickformat=",.2f")
        )
        st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

    with col_data:
        df_display = history.copy()
        df_display['diff'] = df_display['Close'].diff()
        df_display = df_display.sort_index(ascending=False)
        df_display.index = df_display.index.date

        def style_close_col(row):
            color = TOSS_RED if row['diff'] > 0 else TOSS_BLUE if row['diff'] < 0 else TOSS_TEXT_MAIN
            return [f'color: {color}; font-weight: bold' if col == 'Close' else '' for col in row.index]

        st.dataframe(df_display[["Open", "High", "Low", "Close", "diff"]].style.format("{:,.2f}", subset=["Open", "High", "Low", "Close", "diff"]).apply(style_close_col, axis=1), use_container_width=True, height=505)

    st.markdown("---")
    try:
        news_raw = yf.Ticker(ticker).news
        if news_raw:
            pos_items = []
            neg_items = []
            for item in news_raw[:12]:
                title = item.get('title') or item.get('content', {}).get('title', '제목 없음')
                title = translate_title(title)
                link = item.get('link') or item.get('content', {}).get('canonicalUrl', {}).get('url', '#')
                publisher = item.get('publisher') or item.get('content', {}).get('provider', {}).get('displayName', '출처 미상')
                ts = item.get('providerPublishTime')
                date_str = datetime.fromtimestamp(ts).strftime('%m-%d') if ts else (item.get('content', {}).get('pubDate') or "0000-00-00")[5:10]
                news_entry = f"[{date_str}] <a href='{link}' target='_blank' style='text-decoration: none; color: {TOSS_BLUE}; font-weight: 600;'>{title}</a>, ({publisher})"
                
                if analyze_sentiment(title) == "positive":
                    pos_items.append(news_entry)
                else:
                    neg_items.append(news_entry)
            
            col_pos_news, col_neg_news = st.columns(2)
            with col_pos_news:
                st.markdown("🟢 **긍정 / 중립 뉴스**")
                if pos_items: st.markdown("".join([f'<div class="news-item">{item}</div>' for item in pos_items]), unsafe_allow_html=True)
                else: st.caption("분류된 뉴스가 없습니다.")
            with col_neg_news:
                st.markdown("🔴 **부정 뉴스**")
                if neg_items: st.markdown("".join([f'<div class="news-item">{item}</div>' for item in neg_items]), unsafe_allow_html=True)
                else: st.caption("분류된 뉴스가 없습니다.")
        else: st.caption("관련 뉴스가 없습니다.")
    except Exception as e:
        st.info(f"뉴스 데이터를 가져올 수 없습니다. ({e})")

st.markdown("---")
update_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
st.markdown(f"<div style='text-align: right; color: {TOSS_TEXT_SUB}; font-size: 0.8rem;'>정보 업데이트: {update_time}</div>", unsafe_allow_html=True)
