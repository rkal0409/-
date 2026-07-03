"""
매일 아침 미국 증시(나스닥/S&P500) 마감 기준 브리핑을 생성해서 텔레그램으로 보내는 스크립트.
전일 미국장 지수, 관심 섹터(2차전지/반도체/바이오/원전/로봇) 등락률, 관련 뉴스를 담습니다.

필요한 환경변수 (GitHub Actions Secrets에 등록):
  TELEGRAM_BOT_TOKEN   - 텔레그램 봇 토큰 (BotFather에서 발급)
  TELEGRAM_CHAT_ID     - 메시지를 받을 채팅 ID
  NAVER_CLIENT_ID      - 네이버 뉴스 검색 API 클라이언트 ID
  NAVER_CLIENT_SECRET  - 네이버 뉴스 검색 API 시크릿
"""
from __future__ import annotations
import os
import sys
from datetime import datetime

import requests
import yfinance as yf

# ---------------------------------------------------------------------------
# 설정: 여기를 취향에 맞게 수정하세요
# ---------------------------------------------------------------------------

# 미국 주요 지수
INDEXES = {
    "^IXIC": "나스닥종합지수",
    "^GSPC": "S&P500",
}

# 관심 섹터 (국내에 딱 맞는 공식 지수가 없어 대표 미국 상장 ETF로 대체)
#   2차전지 = LIT (Global X Lithium & Battery Tech)
#   반도체  = SOXX (iShares Semiconductor)
#   바이오  = XBI (SPDR S&P Biotech)
#   원전    = NLR (VanEck Uranium+Nuclear Energy)
#   로봇    = BOTZ (Global X Robotics & AI)
SECTORS = {
    "LIT": "2차전지",
    "SOXX": "반도체",
    "XBI": "바이오",
    "NLR": "원전",
    "BOTZ": "로봇",
}

# 뉴스 검색 키워드 (몇 건씩 가져올지)
NEWS_FOR_MARKET = 3       # "나스닥", "S&P500" 등 시장 전반 뉴스
NEWS_PER_SECTOR = 2       # 섹터별 뉴스


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


def build_index_section() -> str:
    lines = ["📊 *전일 미국장 마감*"]
    for ticker, name in INDEXES.items():
        data = fetch_price(ticker)
        if data:
            arrow = "🔴" if data["change"] >= 0 else "🔵"
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
        results.append((name, data))

    # 상승, 하락, 실패 그룹으로 분류
    rising = []
    falling = []
    failed = []

    for name, data in results:
        if data is None:
            failed.append(f"⚠️ {name}: 조회 실패")
        elif data["change"] >= 0:
            rising.append((name, data))
        else:
            falling.append((name, data))

    # 상승은 가장 많이 오른 순서대로, 하락은 가장 많이 떨어진 순서대로 정렬
    rising.sort(key=lambda x: x[1]["pct"], reverse=True)
    falling.sort(key=lambda x: x[1]["pct"])

    lines = ["🔥 *관심 섹터*"]
    lines.append("") # 섹터 제목 아래 빈 줄

    # 상승 박스
    lines.append("📈 *[상승]*")
    if rising:
        for name, data in rising:
            lines.append(f"> 🔴 {name}: {data['pct']:+.2f}%")
    else:
        lines.append("> 상승 섹터 없음")

    lines.append("") # 상승과 하락 사이 간격 띄우기

    # 하락 박스
    lines.append("📉 *[하락]*")
    if falling:
        for name, data in falling:
            lines.append(f"> 🔵 {name}: {data['pct']:+.2f}%")
    else:
        lines.append("> 하락 섹터 없음")

    # 조회 실패가 있을 경우 맨 아래에 추가
    if failed:
        lines.append("")
        lines.extend(failed)

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
    lines = ["📰 *새벽~아침 참고 뉴스*"]

    market_news = fetch_news("미국증시 나스닥 S&P500", NEWS_FOR_MARKET, client_id, client_secret)
    for n in market_news:
        lines.append(f"• {n['title']}")

    for _, name in SECTORS.items():
        sector_news = fetch_news(name, NEWS_PER_SECTOR, client_id, client_secret)
        if sector_news:
            lines.append(f"\n_{name}_")
            for n in sector_news:
                lines.append(f"• {n['title']}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 3. 텔레그램 전송
# ---------------------------------------------------------------------------

def send_telegram(text: str, bot_token: str, chat_id: str) -> None:
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    chat_ids = [c.strip() for c in chat_id.split(",") if c.strip()]
    # 텔레그램 메시지 길이 제한(4096자) 대비 분할 전송
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


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main():
    bot_token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    naver_id = os.environ["NAVER_CLIENT_ID"]
    naver_secret = os.environ["NAVER_CLIENT_SECRET"]

    today = datetime.now().strftime("%Y년 %m월 %d일 (%a)")

    index_section = build_index_section()
    sector_section = build_sector_section()
    news_section = build_news_section(naver_id, naver_secret)

    message = (
        f"☀️ *{today} 아침 프리마켓 브리핑*\n\n"
        f"{index_section}\n\n"
        f"{sector_section}\n\n"
        f"{news_section}"
    )

    send_telegram(message, bot_token, chat_id)
    print("브리핑 발송 완료")


if __name__ == "__main__":
    main()
