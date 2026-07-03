"""
매일 오후 한국 증시(코스피/코스닥) 마감 기준 브리핑을 생성해서 텔레그램으로 보내는 스크립트.
"""

import os
import sys
import collections
from datetime import datetime
from zoneinfo import ZoneInfo
import requests
import yfinance as yf
import holidays
from bs4 import BeautifulSoup

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

# 시총 상위 핵심 주도주 위주의 섹터 사전 (AI가 직접 매핑)
STOCK_SECTOR_MAP = {
    # 반도체
    "삼성전자": "반도체", "SK하이닉스": "반도체", "한미반도체": "반도체", "하나마이크론": "반도체", "리노공업": "반도체", "HPSP": "반도체", "이수페타시스": "반도체", "DB하이텍": "반도체", "ISC": "반도체",
    # 2차전지
    "LG에너지솔루션": "2차전지", "삼성SDI": "2차전지", "포스코퓨처엠": "2차전지", "에코프로": "2차전지", "에코프로비엠": "2차전지", "엘엔에프": "2차전지", "금양": "2차전지", "POSCO홀딩스": "2차전지", "LG화학": "2차전지",
    # 바이오/제약
    "삼성바이오로직스": "바이오", "셀트리온": "바이오", "유한양행": "바이오", "알테오젠": "바이오", "HLB": "바이오", "케어젠": "바이오", "리가켐바이오": "바이오", "삼천당제약": "바이오", "휴젤": "바이오",
    # 자동차/부품
    "현대차": "자동차", "기아": "자동차", "현대모비스": "자동차", "HL만도": "자동차", "한온시스템": "자동차", "현대오토에버": "자동차",
    # 원전/전력
    "두산에너빌리티": "원전/전력", "HD현대일렉트릭": "원전/전력", "LS ELECTRIC": "원전/전력", "효성중공업": "원전/전력", "한국전력": "원전/전력", "일진전기": "원전/전력",
    # 로봇
    "두산로보틱스": "로봇", "레인보우로보틱스": "로봇", "엔젤로보틱스": "로봇",
    # 플랫폼/게임
    "NAVER": "IT/플랫폼", "카카오": "IT/플랫폼", "크래프톤": "IT/플랫폼", "엔씨소프트": "IT/플랫폼", "펄어비스": "IT/플랫폼",
    # 금융
    "KB금융": "금융", "신한지주": "금융", "하나금융지주": "금융", "메리츠금융지주": "금융", "우리금융지주": "금융", "삼성생명": "금융",
    # 방산/조선
    "한화에어로스페이스": "방산/조선", "LIG넥스원": "방산/조선", "현대로템": "방산/조선", "한국항공우주": "방산/조선", "HD한국조선해양": "방산/조선", "HD현대중공업": "방산/조선", "삼성중공업": "방산/조선", "한화오션": "방산/조선",
}

def is_market_open() -> bool:
    today_kst = datetime.now(ZoneInfo("Asia/Seoul")).date()
    if today_kst.weekday() >= 5:
        return False
    kr_holidays = holidays.KR()
    if today_kst in kr_holidays:
        return False
    return True

# ---------------------------------------------------------------------------
# 1. 시세 및 섹터 가져오기
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
            arrow = "🔴" if data["change"] >= 0 else "🔵"
            lines.append(f"{arrow} {name}: {data['price']:,} ({data['change']:+,}, {data['pct']:+.2f}%)")
        else:
            lines.append(f"⚠️ {name}: 조회 실패")
    return "\n".join(lines)

def build_sector_section() -> str:
    results = []
    for ticker, name in SECTORS.items():
        data = fetch_price(ticker)
        results.append((name, data))

    rising, falling, failed = [], [], []

    for name, data in results:
        if data is None:
            failed.append(f"⚠️ {name}: 조회 실패")
        elif data["change"] >= 0:
            rising.append((name, data))
        else:
            falling.append((name, data))

    rising.sort(key=lambda x: x[1]["pct"], reverse=True)
    falling.sort(key=lambda x: x[1]["pct"])

    lines = ["🔥 *관심 섹터*"]
    lines.append("") 

    lines.append("📈 *[상승]*")
    if rising:
        for name, data in rising:
            lines.append(f"> 🔴 {name}: {data['pct']:+.2f}%")
    else:
        lines.append("> 상승 섹터 없음")

    lines.append("") 

    lines.append("📉 *[하락]*")
    if falling:
        for name, data in falling:
            lines.append(f"> 🔵 {name}: {data['pct']:+.2f}%")
    else:
        lines.append("> 하락 섹터 없음")

    if failed:
        lines.append("")
        lines.extend(failed)

    return "\n".join(lines)

# ---------------------------------------------------------------------------
# 2. 외인/기관 수급 트렌드 분석 (네이버 금융 크롤링)
# ---------------------------------------------------------------------------
def extract_top_sectors_from_naver(url: str) -> tuple[str, str]:
    """네이버 금융 페이지에서 매수/매도 종목을 추출하여 가장 많이 등장한 섹터를 반환"""
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        r.encoding = 'euc-kr'
        soup = BeautifulSoup(r.text, 'html.parser')
        
        buy_sectors = []
        sell_sectors = []
        
        for tr in soup.find_all('tr'):
            links = tr.find_all('a', class_='tltle')
            if len(links) == 4:
                # Naver 4열 구조: 코스피 순매수(0), 코스피 순매도(1), 코스닥 순매수(2), 코스닥 순매도(3)
                buy_sectors.append(STOCK_SECTOR_MAP.get(links[0].text.strip()))
                sell_sectors.append(STOCK_SECTOR_MAP.get(links[1].text.strip()))
                buy_sectors.append(STOCK_SECTOR_MAP.get(links[2].text.strip()))
                sell_sectors.append(STOCK_SECTOR_MAP.get(links[3].text.strip()))
            elif len(links) == 2:
                buy_sectors.append(STOCK_SECTOR_MAP.get(links[0].text.strip()))
                sell_sectors.append(STOCK_SECTOR_MAP.get(links[1].text.strip()))

        # None(사전에 없는 종목) 제거
        buy_sectors = [s for s in buy_sectors if s]
        sell_sectors = [s for s in sell_sectors if s]
        
        # 가장 많이 등장한 섹터 2개씩 추출
        top_buys = [item[0] for item in collections.Counter(buy_sectors).most_common(2)]
        top_sells = [item[0] for item in collections.Counter(sell_sectors).most_common(2)]
        
        return (", ".join(top_buys) if top_buys else "혼조세", 
                ", ".join(top_sells) if top_sells else "혼조세")
    except Exception as e:
        print(f"[WARN] 수급 트렌드 크롤링 실패: {e}", file=sys.stderr)
        return ("조회 실패", "조회 실패")

def build_investor_trend_section() -> str:
    # 1. 외국인 순매수/순매도 페이지
    foreigner_url = "https://finance.naver.com/sise/sise_deal_rank.naver"
    f_buys, f_sells = extract_top_sectors_from_naver(foreigner_url)
    
    # 2. 기관 순매수/순매도 페이지
    inst_url = "https://finance.naver.com/sise/sise_deal_rank.naver?investor_gubun=1000"
    i_buys, i_sells = extract_top_sectors_from_naver(inst_url)
    
    lines = ["👥 *오늘의 주체별 수급 동향*"]
    lines.append(f"• 👱‍♂️ *외국인*: [매수] {f_buys} / [매도] {f_sells}")
    lines.append(f"• 🏢 *기 관*: [매수] {i_buys} / [매도] {i_sells}")
    
    return "\n".join(lines)

# ---------------------------------------------------------------------------
# 3. 뉴스 가져오기 (네이버 뉴스 API)
# ---------------------------------------------------------------------------
def fetch_news(query: str, count: int, client_id: str, client_secret: str) -> list[dict]:
    url = "https://openapi.naver.com/v1/search/news.json"
    headers = {
        "X-Naver-Client-Id": client_id,
        "X-Naver-Client-Secret": client_secret,
    }
    # date(최신순)으로 고정하여 과거 자극적인 기사 방지
    params = {"query": query, "display": count, "sort": "date"}
    try:
        r = requests.get(url, headers=headers, params=params, timeout=10)
        r.raise_for_status()
        items = r.json().get("items", [])
        cleaned = []
        for item in items:
            title = item["title"].replace("<b>", "").replace("</b>", "").replace("&quot;", '"').replace("&amp;", "&")
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
# 4. 텔레그램 전송 및 메인
# ---------------------------------------------------------------------------
def send_telegram(text: str, bot_token: str, chat_id: str) -> None:
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    chat_ids = [c.strip() for c in chat_id.split(",") if c.strip()]
    chunks = [text[i : i + 4000] for i in range(0, len(text), 4000)]
    for cid in chat_ids:
        for chunk in chunks:
            r = requests.post(url, data={"chat_id": cid, "text": chunk, "parse_mode": "Markdown"}, timeout=10)
            if not r.ok:
                print(f"[ERROR] 텔레그램 전송 실패({cid}): {r.text}", file=sys.stderr)

def main():
    if not is_market_open():
        print("오늘은 주말 또는 한국 공휴일이므로 마감 브리핑을 발송하지 않습니다.")
        return

    bot_token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    naver_id = os.environ["NAVER_CLIENT_ID"]
    naver_secret = os.environ["NAVER_CLIENT_SECRET"]

    today_kst = datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y년 %m월 %d일")

    index_section = build_index_section()
    sector_section = build_sector_section()
    trend_section = build_investor_trend_section()
    news_section = build_news_section(naver_id, naver_secret)

    message = (
        f"🏁 *{today_kst} 국내 증시 마감 브리핑*\n\n"
        f"{index_section}\n\n"
        f"{trend_section}\n\n"
        f"{sector_section}\n\n"
        f"{news_section}"
    )

    send_telegram(message, bot_token, chat_id)
    print("마감 브리핑 발송 완료")

if __name__ == "__main__":
    main()
