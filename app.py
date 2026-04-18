"""
글로벌 시장 스캐너 — 나스닥 & 코스피 투자 신호 대시보드
개인 교육용 | 투자 권유 아님
"""
import warnings; warnings.filterwarnings("ignore")
import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
from datetime import datetime
import requests, time

st.set_page_config(
    page_title="Market Scanner", page_icon="📡",
    layout="wide", initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=DM+Mono:wght@400;500&family=DM+Sans:wght@400;500&display=swap');
* { box-sizing: border-box; }
html, body, [data-testid="stAppViewContainer"] { background:#06060e !important; color:#e2e2f0; font-family:'DM Sans',system-ui,sans-serif; }
[data-testid="stSidebar"] { display:none; }
[data-testid="stHeader"]  { background:transparent; }
h1,h2,h3 { font-family:'Syne',sans-serif !important; color:#f0f0ff !important; }
.block-container { padding:2rem 2rem 4rem !important; max-width:1200px; }

.section-label { font-family:'DM Mono',monospace; font-size:10px; letter-spacing:.18em; text-transform:uppercase; color:#3a3a58; margin:2rem 0 .75rem; }

.verdict { background:#0e0e1c; border-radius:16px; padding:1.5rem 2rem; margin-bottom:2rem; display:flex; align-items:center; gap:1.5rem; border:1px solid rgba(255,255,255,0.06); }
.verdict-score { font-family:'Syne',sans-serif; font-size:52px; font-weight:800; line-height:1; }
.verdict-label { font-size:16px; font-weight:600; margin-bottom:4px; }
.verdict-sub   { font-size:13px; color:#5a5a7a; }

.detail-box { background:#0e0e1c; border:1px solid rgba(255,255,255,0.08); border-radius:14px; padding:1.5rem; margin-top:.5rem; }
.detail-title { font-family:'Syne',sans-serif; font-size:18px; font-weight:700; margin-bottom:.5rem; }
.detail-desc  { font-size:14px; color:#7070a0; line-height:1.7; margin-bottom:1rem; }
.guide-row { display:flex; gap:8px; flex-wrap:wrap; margin-top:.5rem; }
.guide-pill { font-size:11px; padding:4px 10px; border-radius:20px; font-family:'DM Mono',monospace; }
.pill-green  { background:rgba(34,197,94,.12);  color:#4ade80;  border:.5px solid rgba(34,197,94,.3);  }
.pill-yellow { background:rgba(251,191,36,.12); color:#fde68a; border:.5px solid rgba(251,191,36,.3); }
.pill-red    { background:rgba(248,113,113,.12);color:#fca5a5; border:.5px solid rgba(248,113,113,.3);}

.ts { font-family:'DM Mono',monospace; font-size:10px; color:#2e2e48; text-align:right; margin-top:2rem; }
div[data-testid="stMetric"] { background:transparent !important; border:none !important; }
</style>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════
# 헬퍼 함수
# ══════════════════════════════════════════════════════════════
@st.cache_data(ttl=3601, show_spinner=False)
def fetch_yf(ticker, period="2y"):
    for attempt in range(3):
        try:
            df = yf.Ticker(ticker).history(period=period, auto_adjust=True)
            if not df.empty:
                s = df["Close"]
                return s.squeeze() if isinstance(s, pd.DataFrame) else s
        except Exception:
            time.sleep(2 ** attempt)
    return None

@st.cache_data(ttl=3601, show_spinner=False)
def fetch_fred(series_id, api_key, limit=200):
    url = (f"https://api.stlouisfed.org/fred/series/observations"
           f"?series_id={series_id}&api_key={api_key}"
           f"&file_type=json&sort_order=desc&limit={limit}")
    try:
        r = requests.get(url, timeout=10)
        data = r.json().get("observations", [])
        s = pd.Series({pd.Timestamp(d["date"]): float(d["value"])
                       for d in data if d["value"] != "."}).sort_index()
        return s
    except Exception:
        return None

def calc_rsi(series, period=14):
    delta = series.diff()
    gain  = delta.clip(lower=0).ewm(com=period-1, adjust=False).mean()
    loss  = (-delta.clip(upper=0)).ewm(com=period-1, adjust=False).mean()
    rs    = gain / loss.replace(0, np.nan)
    return 100 - 100 / (1 + rs)

def pos_52w(series):
    h = series.iloc[-252:].max() if len(series) >= 252 else series.max()
    l = series.iloc[-252:].min() if len(series) >= 252 else series.min()
    return float((series.iloc[-1] - l) / (h - l) * 100) if h != l else 50.0

def ma200_pct(series):
    if len(series) < 200: return 0.0
    ma = series.rolling(200).mean().iloc[-1]
    return float((series.iloc[-1] / ma - 1) * 100)

def chg(series, days):
    if len(series) <= days: return 0.0
    return float((series.iloc[-1] / series.iloc[-(days+1)] - 1) * 100)

def sig_color(val, green_fn, red_fn):
    if val is None or (isinstance(val, float) and np.isnan(val)): return "grey"
    if green_fn(val): return "green"
    if red_fn(val):   return "red"
    return "yellow"


# ══════════════════════════════════════════════════════════════
# 지표 계산
# ══════════════════════════════════════════════════════════════
def build_indicators(fred_key):
    ind = {}

    # 1. VIX
    s = fetch_yf("^VIX")
    if s is not None:
        v = float(s.iloc[-1]); pct = float((s <= v).mean() * 100)
        ind["vix"] = dict(val=v, val_str=f"{v:.1f}", series=s, pct_rank=pct,
            signal=sig_color(v, lambda x: x >= 25, lambda x: x <= 15),
            signal_text="공포 구간" if v >= 25 else "탐욕·과열" if v <= 15 else "보통")

    # 2. TNX
    s = fetch_yf("^TNX")
    if s is not None:
        v = float(s.iloc[-1]); c60 = chg(s, 60)
        ind["tnx"] = dict(val=v, val_str=f"{v:.2f}%", series=s, chg60=c60,
            signal=sig_color(c60, lambda x: x < 3, lambda x: x > 8),
            signal_text="금리 안정" if c60 < 3 else "금리 급등 위험" if c60 > 8 else "금리 주의")

    # 3. DXY
    s = fetch_yf("DX-Y.NYB")
    if s is not None:
        v = float(s.iloc[-1]); c20 = chg(s, 20)
        ind["dxy"] = dict(val=v, val_str=f"{v:.1f}", series=s, chg20=c20,
            signal=sig_color(c20, lambda x: x < -0.5, lambda x: x > 2),
            signal_text="달러 약세 (우호적)" if c20 < -0.5 else "달러 강세 (주의)" if c20 > 2 else "달러 중립")

    # 4. HYG/LQD 신용스프레드
    hyg = fetch_yf("HYG"); lqd = fetch_yf("LQD")
    if hyg is not None and lqd is not None:
        ratio = (hyg / lqd).dropna(); c20 = chg(ratio, 20)
        ind["hyg"] = dict(val=float(ratio.iloc[-1]), val_str=f"{ratio.iloc[-1]:.3f}",
            series=ratio, chg20=c20,
            signal=sig_color(c20, lambda x: x > 0.3, lambda x: x < -1),
            signal_text="신용시장 안정" if c20 > 0.3 else "신용 스트레스" if c20 < -1 else "신용 주의")

    # 5. 구리/금 비율
    cu = fetch_yf("HG=F"); gc = fetch_yf("GC=F")
    if cu is not None and gc is not None:
        al = pd.concat([cu, gc], axis=1).ffill().dropna(); al.columns = ["cu","gc"]
        ratio = al["cu"] / al["gc"]; c20 = chg(ratio, 20)
        ind["cu_gold"] = dict(val=float(ratio.iloc[-1]), val_str=f"{ratio.iloc[-1]:.4f}",
            series=ratio, chg20=c20,
            signal=sig_color(c20, lambda x: x > 1, lambda x: x < -2),
            signal_text="경기 회복 기대" if c20 > 1 else "경기 침체 우려" if c20 < -2 else "경기 중립")

    # 6. SOXX
    s = fetch_yf("SOXX")
    if s is not None:
        mg = ma200_pct(s); r = float(calc_rsi(s).iloc[-1]); p = pos_52w(s)
        n = sum([mg > 0, r > 45, p > 40])
        ind["soxx"] = dict(val=float(s.iloc[-1]), val_str=f"${s.iloc[-1]:,.0f}",
            series=s, ma200g=mg, rsi14=r, pos52=p,
            signal="green" if n >= 2 else "red" if n == 0 else "yellow",
            signal_text="반도체 강세" if n >= 2 else "반도체 약세" if n == 0 else "반도체 중립")

    # 7. QQQ
    s = fetch_yf("QQQ")
    if s is not None:
        mg = ma200_pct(s); r = float(calc_rsi(s).iloc[-1]); p = pos_52w(s)
        n = sum([mg > 0, 30 < r < 70, p > 30])
        ind["qqq"] = dict(val=float(s.iloc[-1]), val_str=f"${s.iloc[-1]:,.0f}",
            series=s, ma200g=mg, rsi14=r, pos52=p,
            signal="green" if n >= 2 else "red" if n == 0 else "yellow",
            signal_text="나스닥 상승 추세" if n >= 2 else "나스닥 하락 추세" if n == 0 else "나스닥 중립")

    # 8~10. FRED
    if fred_key:
        tga = fetch_fred("WTREGEN", fred_key)
        if tga is not None and len(tga) > 4:
            v = float(tga.iloc[-1]); c4 = chg(tga, 4)
            ind["tga"] = dict(val=v, val_str=f"${v/1000:.0f}B", series=tga, chg4w=c4,
                signal=sig_color(c4, lambda x: x < -5, lambda x: x > 10),
                signal_text="TGA 감소 (유동성 공급)" if c4 < -5 else "TGA 급증 (유동성 흡수)" if c4 > 10 else "TGA 보통")

        m2 = fetch_fred("M2SL", fred_key)
        if m2 is not None and len(m2) > 12:
            v = float(m2.iloc[-1]); cyoy = chg(m2, 12)
            ind["m2"] = dict(val=v, val_str=f"${v/1000:.1f}T", series=m2, chg_yoy=cyoy,
                signal=sig_color(cyoy, lambda x: x > 2, lambda x: x < -1),
                signal_text="M2 증가 (유동성 확장)" if cyoy > 2 else "M2 감소 (유동성 축소)" if cyoy < -1 else "M2 보통")

        fed = fetch_fred("WALCL", fred_key)
        if fed is not None and len(fed) > 4:
            v = float(fed.iloc[-1]); c4 = chg(fed, 4)
            ind["fed_bs"] = dict(val=v, val_str=f"${v/1e6:.2f}T", series=fed, chg4w=c4,
                signal=sig_color(c4, lambda x: x > 0.2, lambda x: x < -0.5),
                signal_text="QE (돈 풀기)" if c4 > 0.2 else "QT (돈 줄이기)" if c4 < -0.5 else "연준 중립")

    # 11. 원달러
    s = fetch_yf("KRW=X")
    if s is not None:
        v = float(s.iloc[-1]); c20 = chg(s, 20)
        pct = float((s.iloc[-252:] <= v).mean() * 100) if len(s) >= 252 else 50.0
        ind["krw"] = dict(val=v, val_str=f"₩{v:,.0f}", series=s, chg20=c20, pct_rank=pct,
            signal=sig_color(c20, lambda x: x < -1, lambda x: x > 2),
            signal_text="원화 강세 (우호적)" if c20 < -1 else "원화 약세 (외인 이탈)" if c20 > 2 else "환율 중립")

    # 12. 원엔
    krw_s = ind.get("krw", {}).get("series")
    yen_s = fetch_yf("JPY=X")
    if krw_s is not None and yen_s is not None:
        al = pd.concat([krw_s, yen_s], axis=1).ffill().dropna(); al.columns = ["krw","yen"]
        ratio = al["krw"] / al["yen"]; c20 = chg(ratio, 20)
        ind["jpykrw"] = dict(val=float(ratio.iloc[-1]), val_str=f"₩{ratio.iloc[-1]:.2f}/¥",
            series=ratio, chg20=c20,
            signal=sig_color(c20, lambda x: x < -1, lambda x: x > 2),
            signal_text="엔화 약세 (우호적)" if c20 < -1 else "엔화 강세 (자금 이탈)" if c20 > 2 else "엔/원 중립")

    # 13. 코스피
    s = fetch_yf("^KS11")
    if s is not None:
        mg = ma200_pct(s); r = float(calc_rsi(s).iloc[-1]); p = pos_52w(s)
        n = sum([mg > 0, 30 < r < 70, p > 30])
        ind["ks11"] = dict(val=float(s.iloc[-1]), val_str=f"{s.iloc[-1]:,.0f}",
            series=s, ma200g=mg, rsi14=r, pos52=p,
            signal="green" if n >= 2 else "red" if n == 0 else "yellow",
            signal_text="코스피 상승 추세" if n >= 2 else "코스피 하락 추세" if n == 0 else "코스피 중립")

    return ind


# ══════════════════════════════════════════════════════════════
# 메타데이터
# ══════════════════════════════════════════════════════════════
META = {
    "vix": {
        "name": "VIX 공포지수",
        "desc": "시장 참여자들이 향후 30일간 얼마나 큰 변동성을 예상하는지를 0~80 숫자로 나타냅니다. '월가의 공포 계기판'이라 불리며 주가와 반대 방향으로 움직입니다. VIX가 치솟는 공황 상태는 역설적으로 좋은 매수 기회인 경우가 많습니다. 단, 공황이 더 심해질 수도 있으므로 단독으로 사용하면 위험합니다.",
        "guides": [("red","< 15 → 탐욕 (과열, 조심)"),("yellow","15~25 → 보통"),("green","25~35 → 공포 (매수 구간)"),("green","> 35 → 극단적 공포 (저점 근방 가능성)")]
    },
    "tnx": {
        "name": "미 10년물 국채금리",
        "desc": "미국 정부가 10년 만기로 돈을 빌릴 때 내는 이자율입니다. 금리가 오르면 기업 미래 이익의 현재 가치가 낮아져 기술주·성장주에 직격탄이 됩니다. 2022년 금리 급등으로 QQQ -33%, SOXL -80%를 경험했습니다. 금리 수준 자체보다 '변화 속도'가 더 중요합니다.",
        "guides": [("green","60일 변화율 < 3% → 안정적"),("yellow","3~8% → 주의"),("red","> 8% → 급등 (나스닥 위험)")]
    },
    "dxy": {
        "name": "달러 인덱스 (DXY)",
        "desc": "유로·엔·파운드 등 6개 주요 통화 대비 미국 달러의 강도입니다. 달러가 강해지면 글로벌 유동성이 줄어들어 신흥국과 위험자산에 불리합니다. 나스닥과 코스피 모두 달러 약세 환경에서 더 잘 오르는 경향이 있습니다.",
        "guides": [("green","20일 변화율 < -0.5% → 약세 (우호적)"),("yellow","-0.5% ~ 2% → 중립"),("red","> 2% → 강세 (주식 불리)")]
    },
    "hyg": {
        "name": "신용시장 건강도 (HYG/LQD)",
        "desc": "정크본드 ETF(HYG)와 투자등급 채권 ETF(LQD)의 비율입니다. 신용시장은 주식시장보다 1~3개월 먼저 위기를 감지하는 경향이 있어 선행 지표로 활용됩니다. 2008년, 2020년 모두 이 지표가 먼저 경고를 보냈습니다. 비율이 하락하면 채권 시장이 '위험하다'고 판단 중이라는 신호입니다.",
        "guides": [("green","비율 상승 → 신용 건전"),("yellow","횡보 → 중립"),("red","비율 하락 → 신용 스트레스 (주의)")]
    },
    "cu_gold": {
        "name": "구리/금 비율",
        "desc": "구리는 산업·경기에 민감하고, 금은 안전자산입니다. 이 비율이 오르면 투자자들이 '앞으로 경기가 좋아질 것'을 기대한다는 의미입니다. '닥터 코퍼(Dr. Copper)'라는 별명처럼 구리 가격은 경제의 선행 지표입니다. 나스닥과 이 비율은 같은 방향으로 움직이는 경향이 있습니다.",
        "guides": [("green","20일 변화율 > 1% → 경기 기대 상승"),("yellow","-2% ~ 1% → 중립"),("red","< -2% → 경기 침체 우려")]
    },
    "soxx": {
        "name": "반도체 지수 (SOXX)",
        "desc": "엔비디아·TSMC·브로드컴 등 미국 반도체 기업들을 묶은 ETF입니다. 반도체는 기술 사이클의 선행 지표로 나스닥보다 먼저 움직이는 경향이 있습니다. AI 붐 이후 특히 중요해졌으며, SOXL(3배 레버리지)의 기준이 되는 지수이기도 합니다. 200일선, RSI, 52주 위치로 종합 판단합니다.",
        "guides": [("green","200일선 위 + RSI > 45 → 강세"),("yellow","혼재 → 중립"),("red","200일선 아래 + RSI < 45 → 약세")]
    },
    "qqq": {
        "name": "나스닥 100 (QQQ)",
        "desc": "애플·마이크로소프트·엔비디아 등 나스닥 상위 100개 기업의 ETF입니다. TQQQ(3배 레버리지)의 기준 지수이기도 합니다. 200일선 아래에 있다면 장기 하락 추세로, 레버리지 ETF 사용이 매우 위험합니다. RSI 30 이하는 단기 과매도로 반등 가능성이 높고, 70 이상은 과매수로 조정 가능성이 있습니다.",
        "guides": [("green","200일선 위 + RSI 45~65 → 건강한 상승"),("green","RSI < 30 → 과매도 (단기 매수 기회)"),("red","200일선 아래 → 레버리지 금지"),("red","RSI > 70 → 과매수 (조정 가능)")]
    },
    "tga": {
        "name": "TGA 잔고 (미 재무부 계좌)",
        "desc": "미국 정부의 연준 당좌예금 계좌입니다. 세금 신고 마감(4월 15일) 전후에 세금이 걷히면서 TGA 잔고가 급증하고, 시중에서 달러가 수천억 원씩 빠져나갑니다. 반대로 정부가 지출하면 잔고가 줄어들고 유동성이 시장에 공급됩니다. 2023년 4~5월 나스닥 조정도 TGA 급증과 연관이 있었습니다.",
        "guides": [("green","4주 변화율 < -5% → 정부 지출 (유동성 공급)"),("yellow","-5% ~ 10% → 보통"),("red","> 10% → 세금 흡수 (유동성 감소)")]
    },
    "m2": {
        "name": "M2 통화량",
        "desc": "시중에 풀려있는 돈의 총량입니다. 현금, 예금, MMF 등을 포함합니다. M2가 늘면 시중에 돈이 많아져 주식으로 흘러들어갈 가능성이 높아집니다. 2020~2021년 M2가 폭발적으로 증가하면서 나스닥이 급등했고, 2022년 M2 증가세가 꺾이면서 폭락이 찾아왔습니다. 전년 대비 변화율로 판단합니다.",
        "guides": [("green","전년 대비 > 2% → 유동성 확장"),("yellow","-1% ~ 2% → 보통"),("red","< -1% → 유동성 축소 (주의)")]
    },
    "fed_bs": {
        "name": "연준 대차대조표",
        "desc": "연준(미국 중앙은행)이 보유한 자산의 총액입니다. QE(양적완화)를 하면 커지고 시장에 돈이 풀립니다. QT(양적긴축)를 하면 줄어들고 돈이 회수됩니다. 2020~2021년 연준이 대차대조표를 8조 달러 이상으로 2배 늘리면서 나스닥이 폭등했고, QT를 시작한 2022년에 폭락했습니다.",
        "guides": [("green","4주 변화율 > 0.2% → QE (돈 풀기)"),("yellow","-0.5% ~ 0.2% → 중립"),("red","< -0.5% → QT (돈 줄이기 중)")]
    },
    "krw": {
        "name": "원/달러 환율",
        "desc": "1달러를 사기 위해 필요한 원화의 양입니다. 원화가 약해지면(환율 상승) 외국인 투자자들이 코스피에서 돈을 빼갑니다. 외국인 입장에서 주가가 올라도 환율 손실이 생기기 때문입니다. 코스피는 외국인이 시총의 약 30%를 보유하고 있어 외인 동향이 지수에 직접 영향을 줍니다.",
        "guides": [("green","20일 변화율 < -1% → 원화 강세 (외인 유입)"),("yellow","-1% ~ 2% → 중립"),("red","> 2% → 원화 급격 약세 (외인 이탈)")]
    },
    "jpykrw": {
        "name": "원/엔 환율",
        "desc": "엔화 대비 원화의 가치입니다. 엔화가 강해지면 일본 투자자들이 해외 자산을 팔고 본국으로 돌아갑니다. 이를 '엔 캐리 트레이드 청산'이라 하며, 한국을 포함한 신흥국에서 자금이 빠져나가는 원인이 됩니다. 2024년 8월 코스피 폭락의 핵심 원인도 엔화 강세였습니다.",
        "guides": [("green","20일 변화율 < -1% → 엔 약세 (코스피 우호)"),("yellow","-1% ~ 2% → 중립"),("red","> 2% → 엔 강세 (신흥국 자금 이탈)")]
    },
    "ks11": {
        "name": "코스피 지수",
        "desc": "한국 주식시장 전체를 나타내는 지수입니다. 200일 이동평균선이 장기 추세의 핵심 기준선입니다. 200일선 아래에 있다면 레버리지 ETF(KODEX 레버리지 등) 사용이 위험합니다. RSI가 30 이하라면 과매도 구간으로 반등 가능성이 높아집니다. 환율과 함께 종합 판단하는 것이 중요합니다.",
        "guides": [("green","200일선 위 + RSI 45~65 → 상승 추세"),("green","RSI < 30 → 과매도 (반등 가능성)"),("red","200일선 아래 → 하락 추세 주의"),("red","RSI > 70 → 과매수")]
    },
}

COLOR_MAP = {"green":"#22c55e","yellow":"#fbbf24","red":"#f87171","grey":"#4b4b6a"}
EMOJI_MAP = {"green":"🟢","yellow":"🟡","red":"🔴","grey":"⚫"}

LAY = dict(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(8,8,15,0.95)",
           font=dict(color="#6b7280",size=11,family="DM Mono"),
           margin=dict(l=50,r=20,t=10,b=30), hovermode="x unified")
AX  = dict(gridcolor="#151520", showgrid=True, zeroline=False)


def make_chart(series, signal):
    s = series.iloc[-252:] if len(series) > 252 else series
    c = COLOR_MAP.get(signal, "#818cf8")
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=s.index, y=s.values, mode="lines",
        line=dict(color=c, width=1.8),
        fill="tozeroy", fillcolor="rgba(34,197,94,0.08)" if c=="#22c55e" else "rgba(251,191,36,0.08)" if c=="#fbbf24" else "rgba(248,113,113,0.08)" if c=="#f87171" else "rgba(129,140,248,0.08)"))
    fig.update_layout(**LAY, height=170, xaxis=dict(**AX), yaxis=dict(**AX))
    return fig


# ══════════════════════════════════════════════════════════════
# 메인 UI
# ══════════════════════════════════════════════════════════════
st.markdown(
    '<div style="font-family:Syne,sans-serif;font-size:30px;font-weight:800;'
    'color:#f0f0ff;margin-bottom:4px;letter-spacing:-.02em">📡 Market Scanner</div>',
    unsafe_allow_html=True)
st.markdown(
    '<div style="font-size:13px;color:#3a3a58;margin-bottom:1.5rem">'
    '나스닥 & 코스피 투자 신호 대시보드 &nbsp;·&nbsp; 개인 교육용 &nbsp;·&nbsp; 투자 권유 아님</div>',
    unsafe_allow_html=True)

# FRED 키 입력
with st.expander("⚙️ FRED API 키 설정 — TGA·M2·연준 대차대조표 활성화 (선택)"):
    st.markdown("""
**무료 발급:** [fred.stlouisfed.org](https://fred.stlouisfed.org/docs/api/api_key.html) 에서 이메일 인증 후 즉시 발급  
키 없이도 나머지 10개 지표는 정상 작동합니다.
    """)
    fk = st.text_input("FRED API Key", type="password",
                        placeholder="발급받은 키 붙여넣기",
                        value=st.session_state.get("fred_key",""))
    if fk: st.session_state["fred_key"] = fk
fred_key = st.session_state.get("fred_key","")

# 데이터 로드
with st.spinner("📡 데이터 수집 중..."):
    indicators = build_indicators(fred_key)

if not indicators:
    st.error("데이터를 불러오지 못했습니다. 잠시 후 새로고침해 주세요."); st.stop()

# ── 종합 점수 ──────────────────────────────────────────────
sigs = [v["signal"] for v in indicators.values() if v["signal"] != "grey"]
ng, ny, nr = sigs.count("green"), sigs.count("yellow"), sigs.count("red")
nt = len(sigs)
score_val = int(ng / nt * 100) if nt > 0 else 50

if score_val >= 65:
    vc, vl, vs = "#22c55e", "매수 우호적", f"긍정 신호 {ng}개 / 전체 {nt}개"
elif score_val >= 45:
    vc, vl, vs = "#fbbf24", "중립 — 관망", f"긍정 {ng} · 주의 {ny} · 부정 {nr}"
else:
    vc, vl, vs = "#f87171", "매도 / 관망 권고", f"부정 신호 {nr}개 / 전체 {nt}개"

st.markdown(f"""
<div class="verdict">
  <div class="verdict-score" style="color:{vc}">{score_val}</div>
  <div>
    <div class="verdict-label" style="color:{vc}">{vl}</div>
    <div class="verdict-sub">{vs} &nbsp;·&nbsp; 점수 100점 만점</div>
    <div class="verdict-sub" style="margin-top:6px;font-size:11px;color:#2e2e48">
      ⚠ 지표를 참고하여 본인이 판단하세요. 이 점수는 투자 권유가 아닙니다.
    </div>
  </div>
</div>
""", unsafe_allow_html=True)

# ── 세션 상태 ─────────────────────────────────────────────
if "selected" not in st.session_state:
    st.session_state.selected = None

# ── 지표 그룹별 카드 ──────────────────────────────────────
GROUPS = [
    ("공통 매크로",       ["vix","tnx","dxy"]),
    ("유동성 3종 세트",   ["tga","m2","fed_bs"]),
    ("나스닥 전용",       ["hyg","cu_gold","soxx","qqq"]),
    ("코스피 전용",       ["krw","jpykrw","ks11"]),
]

for group_name, keys in GROUPS:
    available = [k for k in keys if k in indicators]
    if not available: continue

    st.markdown(f'<div class="section-label">{group_name}</div>', unsafe_allow_html=True)
    cols = st.columns(len(available))

    for col, key in zip(cols, available):
        d    = indicators[key]
        meta = META.get(key, {})
        sig  = d["signal"]
        em   = EMOJI_MAP.get(sig, "⚫")
        name = meta.get("name", key)
        is_selected = st.session_state.selected == key

        with col:
            # 카드 스타일 버튼
            border_color = COLOR_MAP.get(sig, "#4b4b6a")
            bg = f"{border_color}10" if is_selected else "#0e0e1c"
            st.markdown(f"""
            <div style="background:{bg};border:1px solid {border_color}{'66' if is_selected else '28'};
                border-left:3px solid {border_color};border-radius:12px;
                padding:1rem 1.1rem;margin-bottom:4px;">
              <div style="font-size:11px;color:#4a4a68;text-transform:uppercase;
                letter-spacing:.06em;margin-bottom:6px">{em} {name}</div>
              <div style="font-family:'DM Mono',monospace;font-size:22px;
                font-weight:500;color:#ddddf0;margin-bottom:4px">{d['val_str']}</div>
              <div style="font-size:12px;color:{border_color}">{d.get('signal_text','')}</div>
            </div>
            """, unsafe_allow_html=True)
            if st.button("상세 보기 ↓" if not is_selected else "닫기 ↑",
                          key=f"btn_{key}", use_container_width=True):
                st.session_state.selected = None if is_selected else key
                st.rerun()

    # ── 상세 패널 ──────────────────────────────────────────
    if st.session_state.selected in available:
        key  = st.session_state.selected
        d    = indicators[key]
        meta = META.get(key, {})
        sig  = d["signal"]
        c    = COLOR_MAP.get(sig, "#818cf8")

        st.markdown('<div class="detail-box">', unsafe_allow_html=True)

        left, right = st.columns([3, 2])
        with left:
            st.markdown(
                f'<div class="detail-title" style="color:{c}">'
                f'{meta.get("name",key)} &nbsp;—&nbsp; {d.get("signal_text","")}</div>',
                unsafe_allow_html=True)
            st.markdown(
                f'<div class="detail-desc">{meta.get("desc","")}</div>',
                unsafe_allow_html=True)

            # 판독 가이드 pills
            html = '<div class="guide-row">'
            for gtype, gtxt in meta.get("guides", []):
                gc = {"green":"pill-green","yellow":"pill-yellow","red":"pill-red"}.get(gtype,"pill-green")
                html += f'<span class="guide-pill {gc}">{gtxt}</span>'
            html += '</div>'
            st.markdown(html, unsafe_allow_html=True)

            # 추가 수치
            if "ma200g" in d:
                st.markdown("<br>", unsafe_allow_html=True)
                m1, m2, m3 = st.columns(3)
                m1.metric("200일선 대비",   f"{d['ma200g']:+.1f}%",
                          "위 (상승 추세)" if d["ma200g"] > 0 else "아래 (하락 추세)")
                m2.metric("RSI (14일)",     f"{d['rsi14']:.1f}",
                          "과매도" if d["rsi14"] < 30 else "과매수" if d["rsi14"] > 70 else "정상 범위")
                m3.metric("52주 내 위치",   f"{d['pos52']:.0f}%",
                          "저점 근방" if d["pos52"] < 30 else "고점 근방" if d["pos52"] > 80 else "중간")

            if "chg60" in d:
                st.metric("60일 금리 변화율", f"{d['chg60']:+.2f}%")
            if "chg20" in d and "ma200g" not in d:
                st.metric("20일 변화율", f"{d['chg20']:+.2f}%")
            if "pct_rank" in d:
                st.metric("역사적 퍼센타일",
                          f"{d['pct_rank']:.0f}%",
                          f"과거 {d['pct_rank']:.0f}%의 날보다 {'높음' if key == 'vix' else '낮음'}")
            if "chg4w" in d:
                st.metric("4주 변화율", f"{d['chg4w']:+.2f}%")
            if "chg_yoy" in d:
                st.metric("전년 대비", f"{d['chg_yoy']:+.2f}%")

        with right:
            if "series" in d:
                fig = make_chart(d["series"], sig)
                st.plotly_chart(fig, use_container_width=True,
                                config={"displayModeBar": False})
                st.caption("최근 1년 추이")

        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

# 타임스탬프
st.markdown(
    f'<div class="ts">마지막 업데이트: {datetime.now().strftime("%Y.%m.%d %H:%M")} KST · 1시간 캐시</div>',
    unsafe_allow_html=True)
