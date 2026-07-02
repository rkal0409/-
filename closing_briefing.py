"""
매일 오후 한국 증시(코스피/코스닥) 마감 기준 브리핑을 생성해서 텔레그램으로 보내는 스크립트.
"""

import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo
import requests
import yfinance as yf
import holidays

# ---------------------------------------------------------------------------
# 설정: 국내 주요 지수 및 관심 섹터
# ---------------------------------------------------------------------------
INDEXES = {
    "^KS11": "코스피 (KOSPI)",
    "^KQ11": "코스닥 (KOSDAQ)",
}

# 관심 섹터 (국내 대표 상장 ETF 및 대장주 기준)
SECTORS = {
    "305720.KS": "2차전지",
    "091160.KS": "반도체", 
    "229200.KS": "바이오", 
    "0091P0.KS": "원전",    
    "445680.KS": "로봇",    
}

NEWS_FOR_MARKET = 5 

def is_market_open() -> bool:
    """오늘이 주말이거나 한국 공휴일인지 확인 (KST 기준)"""
    # 깃허브 액션은 UTC 기준이므로 한국 시간(KST)으로 명확히 변환해서 체크
    today_kst = datetime.now(ZoneInfo("Asia/Seoul")).date()
    
    # 1. 주말 체크 (5: 토요일, 6: 일요일)
    if today_kst.weekday() >= 5:
        return False
        
    # 2. 한국 공휴일 체크
    kr_holidays = holidays.KR()
    if today_kst in kr_holidays:
        return False
        
    return True

# ---------------------------------------------------------------------------
# 1. 시세 가져오기
# ---------------------------------------------------------------------------
def fetch_price(ticker: str) -> dict | None:
    try:
        hist = yf.Ticker(ticker).history(period="5d")
        if len(hist) < 2:
            return None
        prev_close = hist["Close"].iloc[-2]
        last_close = hist["Close"].iloc[-1]
        change = last_close - prev_close
        pct = (change / prev_close) * 100
        return {
            "price": round(last_close, 2),
            "change": round(change, 2),
            "pct": round(pct, 2),
        }
    except Exception as e:
        print(f"[WARN] {ticker} 시세 조회 실패: {e}", file=sys.stderr)
        return None

def build_index_section() -> str:
    lines = ["📊 *국내 증시 마감 지수*"]
    for ticker, name in INDEXES.items():
        data = fetch_price(ticker)
        if data:
            arrow = "🔺" if data["change"] >= 0 else "🔻"
            lines.append(
                f"{arrow} {name}: {data['price']:,} ({data['change']:+,}, {data['pct']:+.2f}%)"
            )
        else:
            lines.append(f"⚠️ {name}: 조회 실패")
    return "\n".join(lines)

def build_sector_section() -> str:
    results = []
    for ticker, name in SECTORS.items():
        data = fetch_price(ticker)
        if data:
            results.append((name, data))
        else:
            results.append((name, None))

    results.sort(key=lambda x: (x[1] is None, -(x[1]["pct"] if x[1] else 0)))

    lines = ["🔥 *관심 섹터 (오늘 마감 등락률 순)*"]
    for name, data in results:
        if data:
            arrow = "🔺" if data["change"] >= 0 else "🔻"
            lines.append(f"{arrow} {name}: {data['pct']:+.2f}%")
        else:
            lines.append(f"⚠️ {name}: 조회 실패")
    return "\n".join(lines)

# ---------------------------------------------------------------------------
# 2. 뉴스 가져오기 (네이버 뉴스 검색 API)
# ---------------------------------------------------------------------------
def fetch_news(query: str, count: int, client_id: str, client_secret: str) -> list[dict]:
    url = "https://openapi.naver.com/v1/search/news.json"
    headers = {
        "X-Naver-Client-Id": client_id,
        "X-Naver-Client-Secret": client_secret,
    }
    params = {"query": query, "display": count, "sort": "sim"}
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

def build_news_section(client_id: str, client_secret: str) -> str:
    lines = ["📰 *오늘의 마감 시황 주요 뉴스*"]
    market_news = fetch_news("코스피 코스닥 마감 시황", NEWS_FOR_MARKET, client_id, client_secret)
    for n in market_news:
        lines.append(f"• {n['title']}")
    return "\n".join(lines)

# ---------------------------------------------------------------------------
# 3. 텔레그램 전송 및 메인
# ---------------------------------------------------------------------------
def send_telegram(text: str, bot_token: str, chat_id: str) -> None:
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    chat_ids = [c.strip() for c in chat_id.split(",") if c.strip()]
    chunks = [text[i : i + 4000] for i in range(0, len(text), 4000)]
    for cid in chat_ids:
        for chunk in chunks:
            r = requests.post(
                url,
                data={"chat_id": cid, "text": chunk, "parse_mode": "Markdown"},
                timeout=10,
            )
            if not r.ok:
                print(f"[ERROR] 텔레그램 전송 실패({cid}): {r.text}", file=sys.stderr)

def main():
    # 주말이거나 한국 공휴일이면 알림을 보내지 않고 스크립트 종료
    if not is_market_open():
        print("오늘은 주말 또는 한국 공휴일이므로 마감 브리핑을 발송하지 않습니다.")
        return

    bot_token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    naver_id = os.environ["NAVER_CLIENT_ID"]
    naver_secret = os.environ["NAVER_CLIENT_SECRET"]

    # 브리핑 제목에 들어갈 날짜도 한국 시간(KST)으로 맞춰줌
    today_kst = datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y년 %m월 %d일")

    index_section = build_index_section()
    sector_section = build_sector_section()
    news_section = build_news_section(naver_id, naver_secret)

    message = (
        f"🏁 *{today_kst} 국내 증시 마감 브리핑*\n\n"
        f"{index_section}\n\n"
        f"{sector_section}\n\n"
        f"{news_section}"
    )

    send_telegram(message, bot_token, chat_id)
    print("마감 브리핑 발송 완료")

if __name__ == "__main__":
    main()
