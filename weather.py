"""
오늘/내일 날씨 예보(기온, 습도, 자외선지수, 미세먼지)를 텔레그램으로 보내는 스크립트.
미세먼지는 정확도를 위해 에어코리아(환경부) 공식 측정소 데이터를 사용합니다.
아침 예보 시, Gemini AI가 4살 아이를 위한 완벽한 등원룩을 코디해 줍니다.
"""
from __future__ import annotations
import os
import sys
import time
import requests
import html

LOCATION = "37.6567,126.7367"  # 경기도 김포시 고촌읍 (위도,경도) - 날씨/자외선용
AIRKOREA_STATION = "고촌읍"  # 에어코리아 공식 측정소명 - 미세먼지용

# ---------------------------------------------------------------------------
# 에어코리아 미세먼지 측정소 진단
# ---------------------------------------------------------------------------
def try_station_names(candidates: list[str], service_key: str) -> None:
    url = "http://apis.data.go.kr/B552584/ArpltnInforInqireSvc/getMsrstnAcctoRltmMesureDnsty"
    for name in candidates:
        params = {
            "serviceKey": service_key, "returnType": "json", "numOfRows": 1,
            "pageNo": 1, "stationName": name, "dataTerm": "DAILY", "ver": "1.3",
        }
        try:
            r = requests.get(url, params=params, timeout=10)
            body = r.json()["response"]["body"]
            count = body.get("totalCount", 0)
            print(f"'{name}' -> totalCount={count}" + (f" / {body['items'][0]}" if count else ""))
        except Exception as e:
            print(f"'{name}' -> 오류: {e}")

# ---------------------------------------------------------------------------
# 날씨 및 미세먼지 API 수집
# ---------------------------------------------------------------------------
def fetch_forecast(location: str, api_key: str) -> dict:
    url = "http://api.weatherapi.com/v1/forecast.json"
    params = {"key": api_key, "q": location, "days": 2, "aqi": "no", "alerts": "no", "lang": "ko"}
    r = requests.get(url, params=params, timeout=10)
    r.raise_for_status()
    return r.json()

def fetch_dust(station: str, service_key: str) -> dict | None:
    url = "http://apis.data.go.kr/B552584/ArpltnInforInqireSvc/getMsrstnAcctoRltmMesureDnsty"
    params = {
        "serviceKey": service_key, "returnType": "json", "numOfRows": 1,
        "pageNo": 1, "stationName": station, "dataTerm": "DAILY", "ver": "1.3",
    }
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        body = r.json()["response"]["body"]
        items = body["items"]
        if not items: return None
        item = items[0]
        return {"pm10": item.get("pm10Value"), "pm25": item.get("pm25Value")}
    except Exception as e:
        print(f"[WARN] 에어코리아 미세먼지 조회 실패: {e}", file=sys.stderr)
        return None

def pm_grade(value: float, thresholds: list[tuple[float, str]]) -> str:
    for limit, label in thresholds:
        if value <= limit: return label
    return thresholds[-1][1]

PM10_GRADES = [(30, "좋음"), (80, "보통"), (150, "나쁨"), (float("inf"), "매우나쁨")]
PM25_GRADES = [(15, "좋음"), (35, "보통"), (75, "나쁨"), (float("inf"), "매우나쁨")]

def build_rain_detail(hours: list[dict]) -> str | None:
    rain_hours = [h for h in hours if h.get("chance_of_rain", 0) >= 30 or h.get("will_it_rain") == 1]
    if not rain_hours: return None
    start_time = rain_hours[0]["time"].split(" ")[1]
    start_hour = int(start_time.split(":")[0])
    max_chance = max(h.get("chance_of_rain", 0) for h in rain_hours)
    rain_type = "소나기" if any("소나기" in h["condition"]["text"] for h in rain_hours) else "비"
    period = "오전" if start_hour < 12 else "오후"
    hour12 = start_hour if start_hour <= 12 else start_hour - 12
    if hour12 == 0: hour12 = 12
    return f"{period} {hour12}시 이후 {rain_type} 소식 (최대 {max_chance}%)"

def uv_grade(uv: float) -> str:
    if uv < 3: return "낮음"
    elif uv < 6: return "보통"
    elif uv < 8: return "높음"
    elif uv < 11: return "매우높음"
    else: return "위험"

# ---------------------------------------------------------------------------
# 🎀 Gemini AI 4세 전용 등원룩 스타일리스트 (분량 및 완결성 제어)
# ---------------------------------------------------------------------------
def get_ai_outfit_advice(min_temp: float, max_temp: float, condition: str, rain_detail: str | None, pm10_grade: str | None, pm25_grade: str | None) -> str:
    gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not gemini_key:
        return "👗 (AI 코디 봇: GEMINI_API_KEY가 등록되지 않아 기본 날씨만 제공합니다.)"

    prompt = f"""
    당신은 4살 딸을 키우는 센스 넘치고 다정한 육아맘이자 전문 키즈 스타일리스트입니다.
    오늘의 날씨 데이터를 바탕으로, 어린이집에 등원하는 4살 여자아이를 위한 '오늘의 등원룩'을 생생하게 코디해주세요.

    [오늘의 날씨]
    - 기온: 최저 {min_temp}°C / 최고 {max_temp}°C
    - 하늘 상태: {condition}
    - 강수/비 소식: {rain_detail if rain_detail else '없음'}
    - 미세먼지: {pm10_grade if pm10_grade else '보통'} / 초미세먼지: {pm25_grade if pm25_grade else '보통'}

    [스타일링 필수 고려사항]
    1. 분량 압축 및 완결성: 글이 너무 길어지면 텔레그램 전송 중 강제로 잘리게 됩니다. 투머치토커가 되지 않도록 불필요한 서론은 줄이고, 핵심 코디 내용만 10~12줄 내외로 컴팩트하게 담아 반드시 문장을 완벽하게 끝맺으세요.
    2. 4살 어린이집 맞춤형: 활동하기 편한 소재여야 하며, 실내외 온도차에 대비해 입고 벗기 편한 레이어드(겹쳐입기) 전략을 써주세요.
    3. 구체적인 룩북 묘사: 상의, 하의, 아우터, 신발, 액세서리의 색상과 재질을 눈에 그려지듯 묘사하되, 늘어지지 않게 템포를 조절하세요.
    4. 마크다운 기호(*, _, [, ])는 모두 빼고 귀여운 이모지들을 섞어서 다정하고 읽기 편한 문체로 작성해주세요.
    """

    url = f"https://generativelanguage.googleapis.com/v1/models/gemini-3.5-flash:generateContent?key={gemini_key}"
    
    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            r = requests.post(url, headers={"Content-Type": "application/json"}, json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.7, "maxOutputTokens": 2500},
                "safetySettings": [
                    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"}
                ]
            }, timeout=40)
            
            if r.status_code in [500, 502, 503, 504]:
                time.sleep(2 * attempt)
                continue
                
            if not r.ok:
                return f"👗 (AI 코디 봇: 구글 서버 응답 거절 - 코드 {r.status_code})"
                
            data = r.json()
            candidate = data["candidates"][0]
            text = candidate["content"]["parts"][0]["text"].strip()
            
            finish_reason = candidate.get("finishReason", "")
            if finish_reason == "SAFETY":
                text += "\n\n(⚠️ 구글 AI 알림: 아동 관련 단어로 인해 안전 검열 필터가 작동하여 답변이 강제 중단되었습니다.)"
            elif finish_reason == "MAX_TOKENS":
                text += "\n\n(⚠️ 구글 AI 알림: 답변이 너무 길어 최대 글자 수 제한으로 강제 절단되었습니다.)"
                
            text = text.replace("**", "").replace("##", "").replace("#", "").replace("* ", "• ").replace("`", "'")
            return html.escape(text)
            
        except requests.exceptions.Timeout:
            time.sleep(2 * attempt)
        except Exception:
            return "👗 (AI 코디 봇: 코드를 실행하는 중 오류가 발생했습니다.)"
            
    return "👗 (AI 코디 봇: 현재 구글 서버가 바빠 코디를 불러오지 못했어요. 오늘은 겹쳐 입는 옷을 추천해요!)"

# ---------------------------------------------------------------------------
# 메시지 조립
# ---------------------------------------------------------------------------
def build_today_message(data: dict, dust: dict | None) -> str:
    forecastday = data["forecast"]["forecastday"][0]
    date = forecastday["date"]
    hours = forecastday.get("hour", [])
    day = forecastday["day"]

    condition = day["condition"]["text"]
    max_temp = day["maxtemp_c"]
    min_temp = day["mintemp_c"]
    humidity = day["avghumidity"]
    uv = day["uv"]
    rain_chance = day.get("daily_chance_of_rain", 0)
    rain_detail = build_rain_detail(hours)

    lines = [f"☀️ <b>오늘({date}) 날씨 예보</b>", ""]
    lines.append(f"🌤️ {condition}")
    lines.append(f"🌡️ 최고 {max_temp}°C / 최저 {min_temp}°C")
    lines.append(f"☔ 강수확률 {rain_chance}%" + (f" — {rain_detail}" if rain_detail else ""))
    lines.append(f"💧 습도 {humidity}%")
    lines.append(f"🔆 자외선지수 {uv} ({uv_grade(uv)})")

    pm10_grade, pm25_grade = "보통", "보통"
    if dust:
        pm10_raw, pm25_raw = dust.get("pm10"), dust.get("pm25")
        if pm10_raw and pm10_raw != "-":
            pm10_grade = pm_grade(float(pm10_raw), PM10_GRADES)
            lines.append(f"🌫️ 미세먼지(PM10) {float(pm10_raw):.0f} ({pm10_grade})")
        if pm25_raw and pm25_raw != "-":
            pm25_grade = pm_grade(float(pm25_raw), PM25_GRADES)
            lines.append(f"🌫️ 초미세먼지(PM2.5) {float(pm25_raw):.0f} ({pm25_grade})")
    else:
        lines.append("🌫️ 미세먼지: 조회 실패")

    ai_advice = get_ai_outfit_advice(min_temp, max_temp, condition, rain_detail, pm10_grade, pm25_grade)
    
    lines.append("")
    lines.append("🎀 <b>[AI 스타일리스트의 오늘의 추천 등원룩]</b>")
    lines.append(ai_advice)

    return "\n".join(lines)

def build_tomorrow_message(data: dict) -> str:
    forecastdays = data["forecast"]["forecastday"]
    if len(forecastdays) < 2: return "⚠️ 내일 예보 데이터를 가져오지 못했습니다."
    day = forecastdays[1]["day"]
    date = forecastdays[1]["date"]
    
    lines = [f"🌙 <b>내일({date}) 날씨 예보</b>", ""]
    lines.append(f"🌤️ {day['condition']['text']}")
    lines.append(f"🌡️ 최고 {day['maxtemp_c']}°C / 최저 {day['mintemp_c']}°C")
    lines.append(f"☔ 강수확률 {day.get('daily_chance_of_rain', 0)}%")
    return "\n".join(lines)

# ---------------------------------------------------------------------------
# 전송 및 메인
# ---------------------------------------------------------------------------
def send_telegram(text: str, bot_token: str, chat_id: str) -> None:
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    
    chunks = []
    while len(text) > 4000:
        split_idx = text.rfind("\n\n", 0, 4000)
        if split_idx == -1: split_idx = 4000
        chunks.append(text[:split_idx])
        text = text[split_idx:]
    chunks.append(text)

    for cid in [c.strip() for c in chat_id.split(",") if c.strip()]:
        for chunk in chunks:
            try:
                r = requests.post(url, json={"chat_id": cid, "text": chunk, "parse_mode": "HTML"}, timeout=10)
                if not r.ok: print(f"[🔴 텔레그램 발송 실패] 방({cid}): {r.text}", file=sys.stderr)
            except Exception as e:
                print(f"[🔴 텔레그램 에러]: {e}", file=sys.stderr)

def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ("today", "tomorrow", "stations"):
        print("사용법: python weather.py [today|tomorrow|stations]", file=sys.stderr)
        sys.exit(1)

    mode = sys.argv[1]
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")

    if mode == "stations":
        data_go_kr_key = os.environ.get("DATA_GO_KR_KEY", "")
        candidates = ["고촌", "고촌읍", "김포", "장기", "걸포", "사우", "풍무", "감정", "북변", "운양", "구래"]
        try_station_names(candidates, data_go_kr_key)
        return

    api_key = os.environ.get("WEATHERAPI_KEY", "")
    data = fetch_forecast(LOCATION, api_key)

    if mode == "today":
        data_go_kr_key = os.environ.get("DATA_GO_KR_KEY", "")
        dust = fetch_dust(AIRKOREA_STATION, data_go_kr_key)
        message = build_today_message(data, dust)
    else:
        message = build_tomorrow_message(data)

    send_telegram(message, bot_token, chat_id)
    print(f"{mode} 날씨 예보 발송 완료")

if __name__ == "__main__":
    main()
