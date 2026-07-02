"""
매일 아침 국내 주식 브리핑을 생성해서 텔레그램으로 보내는 스크립트.

필요한 환경변수 (GitHub Actions Secrets에 등록):
  TELEGRAM_BOT_TOKEN   - 텔레그램 봇 토큰 (BotFather에서 발급)
  TELEGRAM_CHAT_ID     - 메시지를 받을 채팅 ID
  NAVER_CLIENT_ID      - 네이버 뉴스 검색 API 클라이언트 ID
  NAVER_CLIENT_SECRET  - 네이버 뉴스 검색 API 시크릿

관심 종목은 아래 WATCHLIST 딕셔너리를 직접 수정하세요.
"""

import os
import sys
from datetime import datetime

import requests
import yfinance as yf

# ---------------------------------------------------------------------------
# 설정: 여기를 취향에 맞게 수정하세요
# ---------------------------------------------------------------------------

# 지수 (yfinance 티커: 코스피=^KS11, 코스닥=^KQ11)
INDEXES = {
    "^KS11": "코스피",
    "^KQ11": "코스닥",
}

# 관심 종목 (yfinance 티커. 코스피는 .KS, 코스닥은 .KQ 접미사)
WATCHLIST = {
    "005930.KS": "삼성전자",
    "000660.KS": "SK하이닉스",
    "035420.KS": "NAVER",
    "005380.KS": "현대차",
}

# 뉴스 검색 키워드 (종목별로 몇 건씩 가져올지)
NEWS_PER_STOCK = 2
NEWS_FOR_MARKET = 3  # "코스피", "미국 증시" 등 시장 전반 뉴스


# ---------------------------------------------------------------------------
# 1. 시세 가져오기
# ---------------------------------------------------------------------------

def fetch_price(ticker: str) -> dict | None:
    """최근 2거래일 종가를 비교해 등락률을 계산."""
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


def build_price_section() -> str:
    lines = []

    lines.append("📊 *지수*")
    for ticker, name in INDEXES.items():
        data = fetch_price(ticker)
        if data:
            arrow = "🔺" if data["change"] >= 0 else "🔻"
            lines.append(
                f"{arrow} {name}: {data['price']:,} ({data['change']:+,}, {data['pct']:+.2f}%)"
            )
        else:
            lines.append(f"⚠️ {name}: 조회 실패")

    lines.append("")
    lines.append("💼 *관심 종목*")
    for ticker, name in WATCHLIST.items():
        data = fetch_price(ticker)
        if data:
            arrow = "🔺" if data["change"] >= 0 else "🔻"
            lines.append(
                f"{arrow} {name}: {data['price']:,}원 ({data['change']:+,}, {data['pct']:+.2f}%)"
            )
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


def build_news_section(client_id: str, client_secret: str) -> str:
    lines = ["📰 *오늘의 뉴스*"]

    market_news = fetch_news("코스피 증시", NEWS_FOR_MARKET, client_id, client_secret)
    for n in market_news:
        lines.append(f"• {n['title']}")

    for ticker, name in WATCHLIST.items():
        stock_news = fetch_news(name, NEWS_PER_STOCK, client_id, client_secret)
        if stock_news:
            lines.append(f"\n_{name}_")
            for n in stock_news:
                lines.append(f"• {n['title']}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 3. 텔레그램 전송
# ---------------------------------------------------------------------------

def send_telegram(text: str, bot_token: str, chat_id: str) -> None:
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    # 텔레그램 메시지 길이 제한(4096자) 대비 분할 전송
    chunks = [text[i : i + 4000] for i in range(0, len(text), 4000)]
    for chunk in chunks:
        r = requests.post(
            url,
            data={"chat_id": chat_id, "text": chunk, "parse_mode": "Markdown"},
            timeout=10,
        )
        if not r.ok:
            print(f"[ERROR] 텔레그램 전송 실패: {r.text}", file=sys.stderr)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main():
    bot_token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    naver_id = os.environ["NAVER_CLIENT_ID"]
    naver_secret = os.environ["NAVER_CLIENT_SECRET"]

    today = datetime.now().strftime("%Y년 %m월 %d일 (%a)")

    price_section = build_price_section()
    news_section = build_news_section(naver_id, naver_secret)

    message = (
        f"☀️ *{today} 아침 증시 브리핑*\n\n"
        f"{price_section}\n\n"
        f"{news_section}"
    )

    send_telegram(message, bot_token, chat_id)
    print("브리핑 발송 완료")


if __name__ == "__main__":
    main()
