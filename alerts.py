"""
1. 네이버 뉴스 검색 API (모든 언론사 대상)
2. 네이버 금융 실시간 속보 페이지 (웹 크롤링)
두 가지를 모두 활용하여 관심 종목/섹터의 '속보' 및 '긴급' 기사만 텔레그램으로 발송합니다.
"""

import os
import sys
import json
import time
import requests
from bs4 import BeautifulSoup

SEEN_FILE = "seen_news.json"

# 보유 종목
STOCK_KEYWORDS = [
    "엘엔에프", "케어젠", "일동제약", "현대오토에버", "지투지바이오",
    "큐리오시스", "리노공업", "엘엔씨바이오", "포스코퓨처엠", "현대차",
    "리가켐바이오", "알테오젠", "HD현대일렉트릭", "이수스페셜티케미컬"
]

# 관심 섹터
SECTOR_KEYWORDS = ["2차전지", "반도체", "바이오", "원전", "로봇"]

ALL_KEYWORDS = STOCK_KEYWORDS + SECTOR_KEYWORDS
SEEN_TTL_SECONDS = 3 * 24 * 60 * 60  # 3일 보관

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
# 소스 1. 네이버 뉴스 검색 API (매일경제 등 모든 언론사 통합 검색)
# ---------------------------------------------------------------------------
def fetch_from_api(query: str, client_id: str, client_secret: str) -> list[dict]:
    url = "https://openapi.naver.com/v1/search/news.json"
    headers = {
        "X-Naver-Client-Id": client_id,
        "X-Naver-Client-Secret": client_secret,
    }
    # OR 연산자(|)를 사용하여 속보 또는 긴급 기사를 넓게 검색 (넉넉하게 20개 추출)
    search_query = f"{query} 속보 | {query} 긴급"
    params = {"query": search_query, "display": 20, "sort": "date"}
    
    try:
        r = requests.get(url, headers=headers, params=params, timeout=10)
        r.raise_for_status()
        items = r.json().get("items", [])
        
        cleaned = []
        for item in items:
            title = item["title"].replace("<b>", "").replace("</b>", "").replace("&quot;", '"').replace("&amp;", "&")
            link = item["link"]
            
            # [핵심] 제목에 반드시 '속보'나 '긴급'이 포함되어야 통과
            if "속보" in title or "긴급" in title:
                cleaned.append({"title": title, "link": link})
        return cleaned
    except Exception as e:
        print(f"[WARN] API 검색 실패 ({query}): {e}", file=sys.stderr)
        return []

# ---------------------------------------------------------------------------
# 소스 2. 네이버 금융 실시간 속보 크롤링
# ---------------------------------------------------------------------------
def fetch_from_finance_board() -> list[dict]:
    url = "https://finance.naver.com/news/news_list.naver?mode=LSS2D&section_id=101&section_id2=258"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    try:
        r = requests.get(url, headers=headers, timeout=10)
        r.raise_for_status()
        r.encoding = "euc-kr"
        
        soup = BeautifulSoup(r.text, "html.parser")
        articles = []
        for a_tag in soup.select(".articleSubject a"):
            title = a_tag.get_text(strip=True)
            link = a_tag["href"]
            if link.startswith("/"):
                link = "https://finance.naver.com" + link
            articles.append({"title": title, "link": link})
        return articles
    except Exception as e:
        print(f"[WARN] 금융 속보 크롤링 실패: {e}", file=sys.stderr)
        return []

# ---------------------------------------------------------------------------
# 텔레그램 전송
# ---------------------------------------------------------------------------
def send_telegram(text: str, bot_token: str, chat_id: str) -> bool:
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    chat_ids = [c.strip() for c in chat_id.split(",") if c.strip()]
    ok_all = True
    for cid in chat_ids:
        r = requests.post(url, data={"chat_id": cid, "text": text, "parse_mode": "Markdown"}, timeout=10)
        if not r.ok:
            print(f"[ERROR] 텔레그램 전송 실패({cid}): {r.text}", file=sys.stderr)
            ok_all = False
    return ok_all

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

    # 기사 중복 수집 방지를 위한 딕셔너리 (URL 기준)
    collected_articles = {}

    # 1. API를 통해 종목/섹터별 기사 수집 (매일경제 등 통합)
    for keyword in ALL_KEYWORDS:
        api_news = fetch_from_api(keyword, naver_id, naver_secret)
        for article in api_news:
            collected_articles[article["link"]] = {"title": article["title"], "keywords": [keyword]}

    # 2. 네이버 금융 속보 크롤링 데이터 수집
    finance_news = fetch_from_finance_board()
    for article in finance_news:
        title = article["title"]
        link = article["link"]
        
        # 관심 키워드가 포함되어 있고, '속보'나 '긴급'이라는 단어가 있는지 검사
        matched_keywords = [kw for kw in ALL_KEYWORDS if kw in title]
        if matched_keywords and ("속보" in title or "긴급" in title):
            if link not in collected_articles:
                collected_articles[link] = {"title": title, "keywords": matched_keywords}
            else:
                collected_articles[link]["keywords"] = list(set(collected_articles[link]["keywords"] + matched_keywords))

    # 3. 텔레그램 발송 처리
    for link, data in collected_articles.items():
        if link in seen:
            continue

        seen[link] = now

        if is_first_run:
            continue
            
        keyword_str = ", ".join(data["keywords"])
        text = f"🚨 *[{keyword_str} 속보]* {data['title']}\n{link}"
        
        if send_telegram(text, bot_token, chat_id):
            new_count += 1

    save_seen(seen)

    if is_first_run:
        print("첫 실행: 기준선 기록 완료 (알림 발송 없음)")
    else:
        print(f"신규 속보 {new_count}건 발송 완료")

if __name__ == "__main__":
    main()
