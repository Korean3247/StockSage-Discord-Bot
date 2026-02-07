# Discord Stock Bot

Discord 서버에서 주가 조회, 포트폴리오 모의투자, 뉴스/알림 기능을 제공하는 Python 기반 봇입니다.

## 주요 기능
- 실시간 주가 조회: `!price <TICKER>`
- 추세/감성 분석: `!trend <TICKER>`, `!sentiment <TICKER>`
- 차트 생성: `!chart <TICKER> [기간]`
- 모의투자: `!buy`, `!sell`, `!sellall`, `!balance`, `!portfolio`, `!pnl`, `!reset`
- 관심종목/가격알림: `!watchlist ...`, `!alert ...`
- 포트폴리오 분석/CSV 다운로드: `!portfolio_analysis`, `!download_portfolio`
- 금융 뉴스/추천: `!news`, `!recommend`
- 도움말: `!help`

## 요구 사항
- Python 3.10+
- Discord Bot Token
- News API Key
- (선택) Redis 서버: 없으면 메모리 캐시로 동작

## 설치
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 환경 변수 설정
`.env.example`을 복사해서 `.env`를 만들고 값을 채우세요.

```bash
cp .env.example .env
```

필수:
- `DISCORD_TOKEN`: Discord Developer Portal에서 발급한 봇 토큰
- `NEWS_API_KEY`: 뉴스 조회용 API 키

선택:
- `ALPHA_VANTAGE_API_KEY`: 현재 코드에서는 필수는 아니지만 추후 기능 확장 대비

## 실행
```bash
python bot.py
```

정상 실행 시 콘솔에 로그인 메시지가 출력됩니다.

## 주요 명령어
- `!price AAPL`: 현재가 및 전일 대비 변동
- `!chart TSLA 1y`: 차트 이미지 생성 (`1d`, `5d`, `1mo`, `3mo`, `6mo`, `1y`, `2y`, `5y`, `10y`, `max`)
- `!buy NVDA 3`: 모의 매수
- `!sell NVDA 1`: 모의 매도
- `!portfolio`: 보유 종목/손익 확인
- `!alert AAPL 200`: 목표가 알림 설정
- `!watchlist MSFT`: 관심종목 추가
- `!download_portfolio`: CSV 다운로드
- `!help`: 전체 사용법

## 데이터 파일 (자동 생성)
실행 중 아래 파일이 자동 생성될 수 있습니다.
- `portfolio.db`: 사용자 잔고/거래/알림/관심종목
- `bot_stats.db`: 서버/유저 통계
- `*_chart.png`, `portfolio_pie.png`, `portfolio_profit.png`, `*_portfolio.csv`: 임시 산출물

## 보안/배포 가이드
- 절대 커밋 금지: `.env`, `*.db`, 실제 사용자 데이터, API 키
- 이 저장소는 `.gitignore`로 민감 파일을 제외하도록 설정되어 있습니다.
- 토큰이 노출된 적이 있으면 즉시 폐기하고 재발급(rotate)하세요.

## 최소 커밋 권장 파일
- `bot.py`
- `requirements.txt`
- `.env.example`
- `.gitignore`
- `README.md`

## 참고
- `discussion_topics.txt`, `learning_topics.txt`는 현재 `bot.py`에서 참조하지 않습니다.
- 운영 기능과 직접 연결된 필수 파일은 아닙니다.
