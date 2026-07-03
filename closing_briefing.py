"""
매일 오후 한국 증시(코스피/코스닥) 마감 기준 브리핑을 생성해서 텔레그램으로 보내는 스크립트.
토스증권 API를 활용하여 실시간 수급 동향을 파악합니다.
"""
from __future__ import annotations
import os
import sys
import collections
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

SECTORS = {
    "305720.KS": "2차전지",
    "091160.KS": "반도체", 
    "229200.KS": "바이오", 
    "0091P0.KS": "원전",    
    "445680.KS": "로봇",    
}

NEWS_FOR_MARKET = 5 

STOCK_SECTOR_MAP = {
    "삼성전자": "반도체", "SK하이닉스": "반도체", "한미반도체": "반도체", "이수페타시스": "반도체", "리노공업": "반도체",
    "LG에너지솔루션": "2차전지", "삼성SDI": "2차전지", "포스코퓨처엠": "2차전지", "에코프로": "2차전지", "에코프로비엠": "2차전지", "엘엔에프": "2차전지",
    "삼성바이오로직스": "바이오", "셀트리온": "바이오", "유한양행": "바이오", "알테오젠": "바이오", "리가켐바이오": "바이오",
    "현대차": "자동차", "기아": "자동차", "현대모비스": "자동차", "현대오토에버": "자동차",
    "두산에너빌리티": "원전/전력", "HD현대일렉트릭": "원전/전력", "LS ELECTRIC": "원전/전력",
    "두산로보틱스": "로봇", "레인보우로보틱스": "로봇",
    "NAVER": "IT/플랫폼", "카카오": "IT/플랫폼", "크래프톤": "IT/플랫폼",
    "KB금융": "금융", "신한지주": "금융",
    "한화에어로스페이스": "방산", "LIG넥스원": "방산", "현대로템": "방산",
}

def is_market_open() -> bool:
    today_kst = datetime.now(ZoneInfo("Asia/Seoul")).date()
    if today_kst.weekday() >= 5:
        return False
    if today_kst in holidays.KR():
        return False
    return True

# ---------------------------------------------------------------------------
# 1. 시세 가져오기
# ---------------------------------------------------------------------------
def fetch_price(ticker: str) -> dict | None:
    try:
        hist = yf.Ticker(ticker).history(period="5d")
        if len(hist) < 2: return None
        prev_close = hist["Close"].iloc[-2]
        last_close = hist["Close"].iloc[-1]
        change = last_close - prev_close
        pct = (change / prev_close) * 100
        return {"price": round(last_close, 2), "change": round(change, 2), "pct": round(pct, 2)}
    except Exception:
        return None

def build_index_section() -> str:
    lines = ["📊 *국내 증시 마감 지수*"]
    for ticker, name in INDEXES.items():
        data = fetch_price(ticker)
        if data:
            arrow = "🔴" if data["change"] >= 0 else "🔵"
            lines.append(f"{arrow} {name}: {data['price']:,} ({data['change']:+,}, {data['pct']:+.2f}%)")
    return "\n".join(lines)

def build_sector_section() -> str:
    results = [(name, fetch_price(ticker)) for ticker, name in SECTORS.items()]
    rising = [x for x in results if x[1] and x[1]["change"] >= 0]
    falling = [x for x in results if x[1] and x[1]["change"] < 0]

    rising.sort(key=lambda x: x[1]["pct"], reverse=True)
    falling.sort(key=lambda x: x[1]["pct"])

    lines = ["🔥 *관심 섹터*", "", "📈 *[상승]*"]
    for name, data in rising:
        lines.append(f"> 🔴 {name}: {data['pct']:+.2f}%")
    if not rising: lines.append("> 상승 섹터 없음")

    lines.extend(["", "📉 *[하락]*"])
    for name, data in falling:
        lines.append(f"> 🔵 {name}: {data['pct']:+.2f}%")
    if not falling: lines.append("> 하락 섹터 없음")

    return "\n".join(lines)

# ---------------------------------------------------------------------------
# 2. 토스증권 API 수급 동향
# ---------------------------------------------------------------------------
def parse_toss_sectors(items: list) -> str:
    sectors = [STOCK_SECTOR_MAP.get(item.get("name", "")) for item in items]
    sectors = [s for s in sectors if s]
    top_sectors = [item[0] for item in collections.Counter(sectors).most_common(2)]
    return ", ".join(top_sectors) if top_sectors else "혼조세"

def build_investor_trend_section() -> str:
    url = "https://api.tossinvest.com/v1/market-trend/investor-trend/domestic"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://www.tossinvest.com/"
    }
    
    try:
        r = requests.get(url, headers=headers, timeout=10)
        r.raise_for_status()
        data = r.json()
        
        # 토스증권 응답 구조에 맞게 리스트 추출 (구조에 따라 키값이 달라질 수 있으므로 유연하게 접근)
        payload = data.get("data", {})
        
        f_buys = parse_toss_sectors(payload.get("foreign", {}).get("buys", []))
        f_sells = parse_toss_sectors(payload.get("foreign", {}).get("sells", []))
        
        i_buys = parse_toss_sectors(payload.get("institution", {}).get("buys", []))
        i_sells = parse_toss_sectors(payload.get("institution", {}).get("sells", []))
        
        lines = ["👥 *오늘의 주체별 수급 동향 (토스증권 실시간)*"]
        lines.append(f"• 👱‍♂️ *외국인*: [매수] {f_buys} / [매도] {f_sells}")
        lines.append(f"• 🏢 *기 관*: [매수] {i_buys} / [매도] {i_sells}")
        return "\n".join(lines)
        
    except Exception as e:
        print(f"[WARN] 토스증권 데이터 파싱 실패: {e}", file=sys.stderr)
        return "👥 *오늘의 주체별 수급 동향*\n조회 실패 (API 차단 또는 구조 변경)"

# ---------------------------------------------------------------------------
# 3. 뉴스 가져오기
# ---------------------------------------------------------------------------
def fetch_news(query: str, count: int, client_id: str, client_secret: str) -> list[dict]:
    url = "https://openapi.naver.com/v1/search/news.json"
    headers = {"X-Naver-Client-Id": client_id, "X-Naver-Client-Secret": client_secret}
    params = {"query": query, "display": count, "sort": "date"}
    try:
        r = requests.get(url, headers=headers, params=params, timeout=10)
        r.raise_for_status()
        cleaned = []
        for item in r.json().get("items", []):
            title = item["title"].replace("<b>", "").replace("</b>", "").replace("&quot;", '"').replace("&amp;", "&")
            cleaned.append({"title": title, "link": item["link"]})
        return cleaned
    except Exception:
        return []

def build_news_section(client_id: str, client_secret: str) -> str:
    lines = ["📰 *오늘의 마감 시황 주요 뉴스*"]
    for n in fetch_news("코스피 코스닥 마감 시황", NEWS_FOR_MARKET, client_id, client_secret):
        lines.append(f"• {n['title']}")
    return "\n".join(lines)

# ---------------------------------------------------------------------------
# 메인
# ---------------------------------------------------------------------------
def main():
    if not is_market_open():
        print("휴장일입니다.")
        return

    # 로컬 환경변수 또는 직접 하드코딩 방식으로 입력
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "여기에_봇토큰_입력")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "여기에_챗ID_입력")
    naver_id = os.environ.get("NAVER_CLIENT_ID", "여기에_네이버ID_입력")
    naver_secret = os.environ.get("NAVER_CLIENT_SECRET", "여기에_네이버시크릿_입력")

    today_kst = datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y년 %m월 %d일")
    message = f"🏁 *{today_kst} 국내 증시 마감 브리핑*\n\n{build_index_section()}\n\n{build_investor_trend_section()}\n\n{build_sector_section()}\n\n{build_news_section(naver_id, naver_secret)}"

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    requests.post(url, data={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}, timeout=10)
    print("발송 완료")

if __name__ == "__main__":
    main()
