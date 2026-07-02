"""
관심 종목/섹터 관련 뉴스 속보를 실시간(5분 주기)으로 감지해서 텔레그램으로 보내는 스크립트.
이미 보낸 기사는 seen_news.json에 기록해서 중복 발송하지 않습니다.

필요한 환경변수 (GitHub Actions Secrets에 등록, 기존 아침 브리핑과 동일한 값 재사용 가능):
  TELEGRAM_BOT_TOKEN
  TELEGRAM_CHAT_ID
  NAVER_CLIENT_ID
  NAVER_CLIENT_SECRET
"""

import os
import sys
import json
import time

import requests

SEEN_FILE = "seen_news.json"

# 보유 종목
STOCK_KEYWORDS = [
    "엘엔에프",
    "케어젠",
    "일동제약",
    "현대오토에버",
    "지투지바이오",
    "큐리오시스",
    "리노공업",
    "엘엔씨바이오",
    "포스코퓨처엠",
    "현대차",
    "리가켐바이오",
    "알테오젠",
    "HD현대일렉트릭",
    "이수스페셜티케미컬",
]

# 관심 섹터
SECTOR_KEYWORDS = ["2차전지", "반도체", "바이오", "원전", "로봇"]

ALL_KEYWORDS = STOCK_KEYWORDS + SECTOR_KEYWORDS

NEWS_PER_KEYWORD = 5          # 키워드당 최신 뉴스 몇 건 확인할지
SEEN_TTL_SECONDS = 3 * 24 * 60 * 60  # seen 기록 보관 기간 (3일)


# ---------------------------------------------------------------------------
# seen_news.json 관리
# ---------------------------------------------------------------------------

def load_seen() -> dict:
    if not os.path.exists(SEEN_FILE):
        return {}
    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[WARN] seen_news.json 로드 실패: {e}", file=sys.stderr)
        return {}


def save_seen(seen: dict) -> None:
    now = time.time()
    pruned = {link: ts for link, ts in seen.items() if now - ts < SEEN_TTL_SECONDS}
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(pruned, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# 뉴스 가져오기
# ---------------------------------------------------------------------------

def fetch_news(query: str, count: int, client_id: str, client_secret: str) -> list[dict]:
    url = "https://openapi.naver.com/v1/search/news.json"
    headers = {
        "X-Naver-Client-Id": client_id,
        "X-Naver-Client-Secret": client_secret,
    }
    params = {"query": query, "display": count, "sort": "date"}
    try:
        r = requests.get(url, headers=headers, params=params, timeout=10)
        r.raise_for_status()
        items = r.json().get("items", [])
        cleaned = []
        for item in items:
            title = (
                item["title"]
                .replace("<b>", "")
                .replace("</b>", "")
                .replace("&quot;", '"')
                .replace("&amp;", "&")
            )
            cleaned.append({"title": title, "link": item["link"]})
        return cleaned
    except Exception as e:
        print(f"[WARN] '{query}' 뉴스 조회 실패: {e}", file=sys.stderr)
        return []


# ---------------------------------------------------------------------------
# 텔레그램 전송
# ---------------------------------------------------------------------------

def send_telegram(text: str, bot_token: str, chat_id: str) -> bool:
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    r = requests.post(
        url,
        data={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
        timeout=10,
    )
    if not r.ok:
        print(f"[ERROR] 텔레그램 전송 실패: {r.text}", file=sys.stderr)
        return False
    return True


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main():
    bot_token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    naver_id = os.environ["NAVER_CLIENT_ID"]
    naver_secret = os.environ["NAVER_CLIENT_SECRET"]

    seen = load_seen()
    is_first_run = len(seen) == 0
    now = time.time()

    new_count = 0

    for keyword in ALL_KEYWORDS:
        articles = fetch_news(keyword, NEWS_PER_KEYWORD, naver_id, naver_secret)
        for article in articles:
            link = article["link"]
            if link in seen:
                continue

            seen[link] = now

            if is_first_run:
                continue

            text = f"🚨 *[{keyword}]* {article['title']}\n{link}"
            if send_telegram(text, bot_token, chat_id):
                new_count += 1

    save_seen(seen)

    if is_first_run:
        print("첫 실행: 기준선 기록 완료 (알림 발송 없음)")
    else:
        print(f"신규 속보 {new_count}건 발송 완료")


if __name__ == "__main__":
    main()
