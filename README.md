# 📡 Market Scanner

나스닥 & 코스피 투자 신호 대시보드  
**개인 교육용 | 투자 권유 아님**

---

## 로컬 실행

```bash
pip install -r requirements.txt
streamlit run app.py
```

---

## 🌐 인터넷 배포 (Streamlit Cloud — 무료)

### 1단계: GitHub 저장소 만들기

1. [github.com](https://github.com) 로그인 → **New repository**
2. 이름: `market-scanner` (아무거나 가능)
3. Public으로 설정
4. 이 폴더의 파일 2개 업로드: `app.py`, `requirements.txt`

### 2단계: Streamlit Cloud 배포

1. [share.streamlit.io](https://share.streamlit.io) 접속
2. GitHub 계정으로 로그인
3. **New app** → 방금 만든 저장소 선택
4. Main file path: `app.py`
5. **Deploy** 클릭

→ 약 1~2분 후 `https://your-app-name.streamlit.app` 주소 생성

### 3단계: FRED API 키 설정 (선택)

- [fred.stlouisfed.org](https://fred.stlouisfed.org/docs/api/api_key.html) 에서 무료 발급
- 앱 화면에서 직접 입력 (브라우저에 저장됨)
- 또는 Streamlit Cloud → Settings → Secrets에 추가:
  ```toml
  FRED_KEY = "your_key_here"
  ```

---

## 지표 목록

| 지표 | 소스 | 카테고리 |
|---|---|---|
| VIX 공포지수 | yfinance | 공통 매크로 |
| 미 10년물 금리 | yfinance | 공통 매크로 |
| 달러 인덱스 DXY | yfinance | 공통 매크로 |
| TGA 잔고 | FRED | 유동성 |
| M2 통화량 | FRED | 유동성 |
| 연준 대차대조표 | FRED | 유동성 |
| 신용시장 HYG/LQD | yfinance | 나스닥 |
| 구리/금 비율 | yfinance | 나스닥 |
| 반도체 SOXX | yfinance | 나스닥 |
| 나스닥 QQQ | yfinance | 나스닥 |
| 원/달러 환율 | yfinance | 코스피 |
| 원/엔 환율 | yfinance | 코스피 |
| 코스피 지수 | yfinance | 코스피 |
