"""
오늘/내일 날씨 예보(기온, 습도, 자외선지수, 미세먼지)를 텔레그램으로 보내는 스크립트.
미세먼지는 정확도를 위해 에어코리아(환경부) 공식 측정소 데이터를 사용합니다.

실행 방법:
  python weather.py today       -> 오늘 예보 (아침 7시용)
  python weather.py tomorrow    -> 내일 예보 (저녁 7시용)

필요한 환경변수 (GitHub Actions Secrets에 등록):
  TELEGRAM_BOT_TOKEN   - 텔레그램 봇 토큰
  TELEGRAM_CHAT_ID     - 메시지를 받을 채팅 ID
  WEATHERAPI_KEY       - weatherapi.com 에서 발급받은 API 키 (날씨/자외선용)
  DATA_GO_KR_KEY       - data.go.kr 에서 발급받은 에어코리아 API 인증키 (Decoding 키, 미세먼지용)
"""

import os
import sys
import requests

LOCATION = "37.6567,126.7367"  # 경기도 김포시 고촌읍 (위도,경도) - 날씨/자외선용
AIRKOREA_STATION = "고촌읍"  # 에어코리아 공식 측정소명 - 미세먼지용

def try_station_names(candidates: list[str], service_key: str) -> None:
    """이미 승인된 API로 후보 측정소명들을 하나씩 테스트해서 결과 출력 (진단용)."""
    url = "http://apis.data.go.kr/B552584/ArpltnInforInqireSvc/getMsrstnAcctoRltmMesureDnsty"
    for name in candidates:
        params = {
            "serviceKey": service_key,
            "returnType": "json",
            "numOfRows": 1,
            "pageNo": 1,
            "stationName": name,
            "dataTerm": "DAILY",
            "ver": "1.3",
        }
        try:
            r = requests.get(url, params=params, timeout=10)
            body = r.json()["response"]["body"]
            count = body.get("totalCount", 0)
            print(f"'{name}' -> totalCount={count}" + (f" / {body['items'][0]}" if count else ""))
        except Exception as e:
            print(f"'{name}' -> 오류: {e}")

def outfit_advice(min_temp: float, max_temp: float, rain_detail: str | None, pm10_grade: str | None, pm25_grade: str | None) -> str:
    """평균기온 기준 옷차림 추천 (아이 기준, 어른 가이드보다 살짝 가볍게)."""
    avg_temp = (min_temp + max_temp) / 2

    if avg_temp >= 28:
        clothes = "민소매/반팔 + 반바지, 통풍 잘 되는 얇은 원단"
    elif avg_temp >= 23:
        clothes = "반팔 + 얇은 반바지 또는 면바지"
    elif avg_temp >= 20:
        clothes = "얇은 긴팔 + 바지, 아침저녁 쌀쌀하면 얇은 가디건 하나"
    elif avg_temp >= 17:
        clothes = "맨투맨/얇은 니트 + 바지, 겉에 걸칠 얇은 자켓 하나 챙기기"
    elif avg_temp >= 12:
        clothes = "니트/맨투맨 + 자켓 또는 얇은 점퍼"
    elif avg_temp >= 9:
        clothes = "도톰한 니트 + 점퍼, 목이 시릴 수 있어 목도리 하나"
    elif avg_temp >= 5:
        clothes = "기모 안감 옷 + 코트/두꺼운 점퍼, 장갑 챙기기"
    else:
        clothes = "패딩 + 내복(히트텍), 목도리·장갑·모자 풀장착"

    extras = []
    if rain_detail:
        extras.append(f"{rain_detail} → 우산/우비, 여벌 양말 챙기기")

    bad_dust = pm10_grade in ("나쁨", "매우나쁨") or pm25_grade in ("나쁨", "매우나쁨")
    if bad_dust:
        extras.append("미세먼지 나쁨 → 마스크 챙기고 바깥놀이는 짧게")

    lines = [f"👕 *오늘 옷차림 추천*: {clothes}"]
    if extras:
        lines.append("💡 " + " / ".join(extras))

    return "\n".join(lines)

def fetch_forecast(location: str, api_key: str) -> dict:
    url = "http://api.weatherapi.com/v1/forecast.json"
    params = {
        "key": api_key,
        "q": location,
        "days": 2,
        "aqi": "no",
        "alerts": "no",
        "lang": "ko",
    }
    r = requests.get(url, params=params, timeout=10)
    r.raise_for_status()
    return r.json()


def fetch_dust(station: str, service_key: str) -> dict | None:
    """에어코리아 측정소별 실시간 미세먼지 데이터 조회."""
    url = "http://apis.data.go.kr/B552584/ArpltnInforInqireSvc/getMsrstnAcctoRltmMesureDnsty"
    params = {
        "serviceKey": service_key,
        "returnType": "json",
        "numOfRows": 1,
        "pageNo": 1,
        "stationName": station,
        "dataTerm": "DAILY",
        "ver": "1.3",
    }
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        body = r.json()["response"]["body"]
        items = body["items"]
        if not items:
            print(f"[DEBUG] 에어코리아 응답에 items 없음. 전체 응답: {r.text[:500]}", file=sys.stderr)
            return None
        item = items[0]
        return {
            "pm10": item.get("pm10Value"),
            "pm25": item.get("pm25Value"),
        }
    except Exception as e:
        print(f"[WARN] 에어코리아 미세먼지 조회 실패: {e}", file=sys.stderr)
        return None


def pm_grade(value: float, thresholds: list[tuple[float, str]]) -> str:
    for limit, label in thresholds:
        if value <= limit:
            return label
    return thresholds[-1][1]


PM10_GRADES = [(30, "좋음"), (80, "보통"), (150, "나쁨"), (float("inf"), "매우나쁨")]
PM25_GRADES = [(15, "좋음"), (35, "보통"), (75, "나쁨"), (float("inf"), "매우나쁨")]


def build_rain_detail(hours: list[dict]) -> str | None:
    """시간별 예보에서 비/소나기 시작 시각과 강수확률을 뽑아냄."""
    rain_hours = [h for h in hours if h.get("chance_of_rain", 0) >= 30 or h.get("will_it_rain") == 1]
    if not rain_hours:
        return None

    start_time = rain_hours[0]["time"].split(" ")[1]  # "HH:MM"
    start_hour = int(start_time.split(":")[0])
    max_chance = max(h.get("chance_of_rain", 0) for h in rain_hours)
    is_shower = any("소나기" in h["condition"]["text"] for h in rain_hours)
    rain_type = "소나기" if is_shower else "비"

    period = "오전" if start_hour < 12 else "오후"
    hour12 = start_hour if start_hour <= 12 else start_hour - 12
    if hour12 == 0:
        hour12 = 12

    return f"{period} {hour12}시 이후 {rain_type} 소식 (강수확률 최대 {max_chance}%)"

def uv_grade(uv: float) -> str:
    if uv < 3:
        return "낮음"
    elif uv < 6:
        return "보통"
    elif uv < 8:
        return "높음"
    elif uv < 11:
        return "매우높음"
    else:
        return "위험"


def build_today_message(data: dict, dust: dict | None) -> str:
    forecastday = data["forecast"]["forecastday"][0]
    day = forecastday["day"]
    date = forecastday["date"]
    hours = forecastday.get("hour", [])

    condition = day["condition"]["text"]
    max_temp = day["maxtemp_c"]
    min_temp = day["mintemp_c"]
    humidity = day["avghumidity"]
    uv = day["uv"]
    rain_chance = day.get("daily_chance_of_rain", 0)
    rain_detail = build_rain_detail(hours)

    lines = [f"☀️ *오늘({date}) 날씨 예보*", ""]
    lines.append(f"🌤️ {condition}")
    lines.append(f"🌡️ 최고 {max_temp}°C / 최저 {min_temp}°C")
    lines.append(f"☔ 강수확률 {rain_chance}%" + (f" — {rain_detail}" if rain_detail else ""))
    lines.append(f"💧 습도 {humidity}%")
    lines.append(f"🔆 자외선지수 {uv} ({uv_grade(uv)})")

    pm10_grade = None
    pm25_grade = None

    if dust:
        pm10_raw = dust.get("pm10")
        pm25_raw = dust.get("pm25")
        if pm10_raw and pm10_raw != "-":
            pm10 = float(pm10_raw)
            pm10_grade = pm_grade(pm10, PM10_GRADES)
            lines.append(f"🌫️ 미세먼지(PM10) {pm10:.0f} ({pm10_grade})")
        if pm25_raw and pm25_raw != "-":
            pm25 = float(pm25_raw)
            pm25_grade = pm_grade(pm25, PM25_GRADES)
            lines.append(f"🌫️ 초미세먼지(PM2.5) {pm25:.0f} ({pm25_grade})")
        if (not pm10_raw or pm10_raw == "-") and (not pm25_raw or pm25_raw == "-"):
            lines.append("🌫️ 미세먼지: 측정소 자료 없음")
    else:
        lines.append("🌫️ 미세먼지: 조회 실패")

    lines.append("")
    lines.append(outfit_advice(min_temp, max_temp, rain_detail, pm10_grade, pm25_grade))

    return "\n".join(lines)


def build_tomorrow_message(data: dict) -> str:
    forecastdays = data["forecast"]["forecastday"]
    if len(forecastdays) < 2:
        return "⚠️ 내일 예보 데이터를 가져오지 못했습니다."

    day = forecastdays[1]["day"]
    date = forecastdays[1]["date"]

    condition = day["condition"]["text"]
    max_temp = day["maxtemp_c"]
    min_temp = day["mintemp_c"]
    rain_chance = day.get("daily_chance_of_rain", 0)
    humidity = day["avghumidity"]

    lines = [f"🌙 *내일({date}) 날씨 예보*", ""]
    lines.append(f"🌤️ {condition}")
    lines.append(f"🌡️ 최고 {max_temp}°C / 최저 {min_temp}°C")
    lines.append(f"☔ 강수확률 {rain_chance}%")
    lines.append(f"💧 습도 {humidity}%")

    return "\n".join(lines)


def send_telegram(text: str, bot_token: str, chat_id: str) -> None:
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    chat_ids = [c.strip() for c in chat_id.split(",") if c.strip()]
    for cid in chat_ids:
        r = requests.post(
            url,
            data={"chat_id": cid, "text": text, "parse_mode": "Markdown"},
            timeout=10,
        )
        if not r.ok:
            print(f"[ERROR] 텔레그램 전송 실패({cid}): {r.text}", file=sys.stderr)


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ("today", "tomorrow", "stations"):
        print("사용법: python weather.py [today|tomorrow|stations]", file=sys.stderr)
        sys.exit(1)

    mode = sys.argv[1]

    bot_token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]

    if mode == "stations":
        data_go_kr_key = os.environ["DATA_GO_KR_KEY"]
        candidates = ["고촌", "고촌읍", "김포", "장기", "걸포", "사우", "풍무", "감정", "북변", "운양", "구래"]
        try_station_names(candidates, data_go_kr_key)
        return

    api_key = os.environ["WEATHERAPI_KEY"]
    data = fetch_forecast(LOCATION, api_key)

    if mode == "today":
        data_go_kr_key = os.environ["DATA_GO_KR_KEY"]
        dust = fetch_dust(AIRKOREA_STATION, data_go_kr_key)
        message = build_today_message(data, dust)
    else:
        message = build_tomorrow_message(data)

    send_telegram(message, bot_token, chat_id)
    print(f"{mode} 날씨 예보 발송 완료")


if __name__ == "__main__":
    main()
