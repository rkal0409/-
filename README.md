# 매일 아침 주식 브리핑 (텔레그램)

매일 아침 정해진 시간에 코스피/코스닥 지수, 관심 종목 시세, 관련 뉴스를 텔레그램으로 자동 발송합니다. (완전 무료)

## 준비물 (전부 무료)

| 항목 | 발급처 |
|---|---|
| 텔레그램 봇 토큰 | 텔레그램 @BotFather |
| 텔레그램 채팅 ID | 텔레그램 @userinfobot |
| 네이버 뉴스 검색 API 키 | https://developers.naver.com/apps |
| GitHub 계정 | https://github.com |

## 설정 순서

### 1. 텔레그램 봇 만들기
1. 텔레그램 앱에서 `@BotFather` 검색 후 대화 시작
2. `/newbot` 입력 → 봇 이름과 아이디(예: `my_stock_bot`) 설정
3. 발급되는 토큰을 복사해둠 (예: `123456789:ABCdefGhIJKlmNoPQRstuVWXyz`) → 이게 `TELEGRAM_BOT_TOKEN`
4. 방금 만든 내 봇과 대화창을 열고 아무 메시지나 하나 보내기 (예: "안녕")
   - 이 단계가 없으면 봇이 나에게 메시지를 보낼 수 없어요.

### 2. 내 채팅 ID 확인
1. 텔레그램에서 `@userinfobot` 검색 후 대화 시작
2. `/start` 입력하면 내 `Id` 값이 표시됨 → 이게 `TELEGRAM_CHAT_ID`

### 3. 네이버 뉴스 검색 API 키 발급
1. https://developers.naver.com/apps 접속 → 로그인 → "애플리케이션 등록"
2. 사용 API: "검색" 선택
3. 등록 후 발급되는 `Client ID`, `Client Secret` 복사해둠

### 4. GitHub에 이 코드 올리기
1. GitHub에서 새 저장소(Repository) 생성 (Private으로 설정 권장)
2. 이 폴더(`stock-briefing`) 안의 파일들을 그 저장소에 업로드
   - 터미널 사용 시:
     ```bash
     cd stock-briefing
     git init
     git add .
     git commit -m "daily stock briefing"
     git branch -M main
     git remote add origin <내 저장소 URL>
     git push -u origin main
     ```
   - 또는 GitHub 웹사이트에서 "Add file → Upload files"로 드래그 앤 드롭

### 5. GitHub Secrets 등록
저장소 → Settings → Secrets and variables → Actions → "New repository secret" 에서 아래 4개를 각각 등록:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `NAVER_CLIENT_ID`
- `NAVER_CLIENT_SECRET`

### 6. 테스트 실행
1. 저장소 → Actions 탭 → "Daily Stock Briefing" 워크플로우 선택
2. "Run workflow" 버튼으로 수동 실행
3. 1~2분 후 텔레그램으로 메시지가 오는지 확인

성공하면, 이후로는 매일 한국시간 아침 7시 30분에 자동으로 발송됩니다.

## 커스터마이징

- **관심 종목 변경**: `briefing.py` 안의 `WATCHLIST` 딕셔너리 수정
  - 티커는 `종목코드.KS`(코스피) 또는 `종목코드.KQ`(코스닥) 형식
  - 예: 카카오 → `035720.KS`
- **발송 시간 변경**: `.github/workflows/daily-briefing.yml`의 `cron` 값 수정
  - GitHub Actions는 UTC 기준이므로 `한국시간 - 9시간`으로 계산
  - 예: 아침 8시에 받고 싶다면 → `0 23 * * *`
- **뉴스 개수**: `briefing.py` 상단의 `NEWS_PER_STOCK`, `NEWS_FOR_MARKET` 값 수정

## 참고사항

- 주말/공휴일에는 시세가 전 거래일 기준으로 나올 수 있어요 (원한다면 주중에만 실행되도록 cron 조건을 추가할 수 있습니다)
- GitHub Actions 무료 티어는 public 저장소는 무제한, private 저장소는 매달 2,000분 무료 제공 (이 스크립트는 하루 1~2분이면 충분해서 여유롭습니다)
