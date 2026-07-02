"""
오늘/내일 날씨 예보(기온, 습도, 자외선지수, 미세먼지)를 텔레그램으로 보내는 스크립트.

실행 방법:
  python weather.py today       -> 오늘 예보 (아침 7시용)
  python weather.py tomorrow    -> 내일 예보 (저녁 7시용)

필요한 환경변수 (GitHub Actions Secrets에 등록):
  TELEGRAM_BOT_TOKEN   - 텔레그램 봇 토큰
  TELEGRAM_CHAT_ID     - 메시지를 받을 채팅 ID
  WEATHERAPI_KEY       - weatherapi.com 에서 발급받은 API 키
"""

import os
import sys
import requests

LOCATION = "37.6567,126.7367"  # 다른 지역으로 바꾸고 싶으면 여기만 수정 (예: "Busan", "Incheon")


def fetch_forecast(location: str, api_key: str) -> dict:
    url = "http://api.weatherapi.com/v1/forecast.json"
    params = {
        "key": api_key,
        "q": location,
        "days": 2,
        "aqi": "yes",
        "alerts": "no",
        "lang": "ko",
    }
    r = requests.get(url, params=params, timeout=10)
    r.raise_for_status()
    return r.json()


def pm_grade(value: float, thresholds: list[tuple[float, str]]) -> str:
    for limit, label in thresholds:
        if value <= limit:
            return label
    return thresholds[-1][1]


PM10_GRADES = [(30, "좋음"), (80, "보통"), (150, "나쁨"), (float("inf"), "매우나쁨")]
PM25_GRADES = [(15, "좋음"), (35, "보통"), (75, "나쁨"), (float("inf"), "매우나쁨")]


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


def build_today_message(data: dict) -> str:
    day = data["forecast"]["forecastday"][0]["day"]
    date = data["forecast"]["forecastday"][0]["date"]
    aqi = day.get("air_quality", {})

    condition = day["condition"]["text"]
    max_temp = day["maxtemp_c"]
    min_temp = day["mintemp_c"]
    humidity = day["avghumidity"]
    uv = day["uv"]
    rain_chance = day.get("daily_chance_of_rain", 0)

    pm10 = aqi.get("pm10")
    pm2_5 = aqi.get("pm2_5")

    lines = [f"☀️ *오늘({date}) 날씨 예보*", ""]
    lines.append(f"🌤️ {condition}")
    lines.append(f"🌡️ 최고 {max_temp}°C / 최저 {min_temp}°C")
    lines.append(f"☔ 강수확률 {rain_chance}%")
    lines.append(f"💧 습도 {humidity}%")
    lines.append(f"🔆 자외선지수 {uv} ({uv_grade(uv)})")

    if pm10 is not None:
        lines.append(f"🌫️ 미세먼지(PM10) {pm10:.0f} ({pm_grade(pm10, PM10_GRADES)})")
    if pm2_5 is not None:
        lines.append(f"🌫️ 초미세먼지(PM2.5) {pm2_5:.0f} ({pm_grade(pm2_5, PM25_GRADES)})")

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
    r = requests.post(
        url,
        data={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
        timeout=10,
    )
    if not r.ok:
        print(f"[ERROR] 텔레그램 전송 실패: {r.text}", file=sys.stderr)


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ("today", "tomorrow"):
        print("사용법: python weather.py [today|tomorrow]", file=sys.stderr)
        sys.exit(1)

    mode = sys.argv[1]

    bot_token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    api_key = os.environ["WEATHERAPI_KEY"]

    data = fetch_forecast(LOCATION, api_key)

    if mode == "today":
        message = build_today_message(data)
    else:
        message = build_tomorrow_message(data)

    send_telegram(message, bot_token, chat_id)
    print(f"{mode} 날씨 예보 발송 완료")


if __name__ == "__main__":
    main()
