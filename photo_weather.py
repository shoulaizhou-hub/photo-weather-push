import requests
import schedule
import time
import os
from datetime import datetime, timedelta

# ====================== 配置区：修改成你自己的信息 ======================
# 支持从环境变量读取配置（用于GitHub Actions）
QWEATHER_KEY = os.getenv("QWEATHER_KEY", "2917c17f24104f1ea609f60866e9051b")       # 和风天气开发者KEY
QWEATHER_HOST = os.getenv("QWEATHER_HOST", "p34nmvjx6h.re.qweatherapi.com")         # 专属API Host

CITIES = [
    {"id": "101200101", "name": "武汉", "bot_name": "武汉"},
    {"id": "101010500", "name": "北京朝阳", "bot_name": "北京"}
]

PUSH_METHOD = os.getenv("PUSH_METHOD", "pushplus")               # 推送方式："pushplus" 或 "bottalk"
PUSHPLUS_TOKEN = os.getenv("PUSHPLUS_TOKEN", "1406f96290624ee1819b4c4f2237759c")                   # PushPlus的用户Token
BOTTALK_SENDKEY = os.getenv("BOTTALK_SENDKEY", "")                   # BotTalk的SendKey（免费方案）
DAILY_PUSH_TIME = os.getenv("DAILY_PUSH_TIME", "20:00")              # 每日推送时间（建议晚上推送次日预报）
GROUP_TOPIC = os.getenv("GROUP_TOPIC", "")                       # PushPlus群组名（为空则只推送自己）
# ======================================================================

BASE_URL = f"https://{QWEATHER_HOST}" if QWEATHER_HOST else "https://devapi.qweather.com"
FALLBACK_URL = "https://devapi.qweather.com"

DAILY_URL = f"{BASE_URL}/v7/weather/3d"
HOURLY_URL = f"{BASE_URL}/v7/weather/24h"
AIR_URL = f"{BASE_URL}/v7/air/now"

HEADERS = {"X-QW-Api-Key": QWEATHER_KEY, "Accept": "application/json"}


def qweather_request(url, params, fallback_url=None):
    """和风天气请求，支持失败回退"""
    try:
        res = requests.get(url, params=params, headers=HEADERS).json()
        if "error" in res or res.get("code") != "200":
            if fallback_url and fallback_url != url:
                print(f"专属Host请求失败，尝试回退到公共地址...")
                fallback_res = requests.get(fallback_url, params=params, headers=HEADERS).json()
                if fallback_res.get("code") == "200":
                    return fallback_res
            return res
        return res
    except Exception as e:
        if fallback_url and fallback_url != url:
            try:
                return requests.get(fallback_url, params=params, headers=HEADERS).json()
            except:
                pass
        print(f"请求失败: {e}")
        return None


def get_daily_weather(city_id, day_offset=1):
    """获取指定天数后的天气数据（day_offset=0为今天，=1为明天）"""
    params = {"location": city_id}
    fallback_daily = f"{FALLBACK_URL}/v7/weather/3d"
    res = qweather_request(DAILY_URL, params, fallback_daily)
    if not res or res.get("code") != "200":
        if "error" in res:
            print(f"API错误: {res['error']['title']} - {res['error']['detail']}")
        else:
            print(f"API返回错误码: {res.get('code')}")
        return None
    target_day = res["daily"][day_offset] if day_offset < len(res["daily"]) else res["daily"][-1]
    return {
        "sunrise": target_day["sunrise"],
        "sunset": target_day["sunset"],
        "text_day": target_day["textDay"],
        "temp_max": target_day["tempMax"],
        "temp_min": target_day["tempMin"],
        "cloud": int(target_day.get("cloud", 0)),
        "humidity": int(target_day.get("humidity", 0)),
        "precip": float(target_day.get("precip", 0)),
        "wind_speed": float(target_day.get("windSpeed", 0)),
        "date": target_day["fxDate"]
    }


def get_hourly_weather(city_id, target_hour):
    """获取指定小时的气象数据"""
    params = {"location": city_id}
    fallback_hourly = f"{FALLBACK_URL}/v7/weather/24h"
    res = qweather_request(HOURLY_URL, params, fallback_hourly)
    if not res or res.get("code") != "200":
        return None
    for hour_data in res["hourly"]:
        fx_time = datetime.strptime(hour_data["fxTime"], "%Y-%m-%dT%H:%M%z")
        if fx_time.hour == target_hour:
            return {
                "cloud": int(hour_data["cloud"]),
                "humidity": int(hour_data["humidity"]),
                "wind_speed": float(hour_data["windSpeed"]),
                "precip": float(hour_data["precip"]),
                "text": hour_data["text"]
            }
    return res["hourly"][0]


def get_air_quality(city_id):
    """获取实时空气质量AQI"""
    params = {"location": city_id}
    fallback_air = f"{FALLBACK_URL}/v7/air/now"
    res = qweather_request(AIR_URL, params, fallback_air)
    if not res or res.get("code") != "200":
        return 50
    return int(res["now"]["aqi"])


def get_sunsetbot_data(city, event_type):
    """获取sunsetbot火烧云预报数据"""
    import random
    query_id = random.randint(100000, 999999)
    url = f"https://sunsetbot.top/?intend=select_city&query_city={city}&event={event_type}&model=GFS&query_id={query_id}"
    try:
        res = requests.get(url, timeout=10).json()
        if res.get("status") != "ok":
            return None
        
        quality_text = res.get("tb_quality", "0")
        aod_text = res.get("tb_aod", "0")
        
        import re
        quality_match = re.search(r'([\d.]+)', quality_text)
        aod_match = re.search(r'([\d.]+)', aod_text)
        
        quality = float(quality_match.group(1)) if quality_match else 0
        aod = float(aod_match.group(1)) if aod_match else 0
        
        quality_label = re.search(r'（(.+?)）', quality_text)
        aod_label = re.search(r'（(.+?)）', aod_text)
        
        quality_label = quality_label.group(1) if quality_label else ""
        aod_label = aod_label.group(1) if aod_label else ""
        
        return {
            "quality": quality,
            "quality_label": quality_label,
            "aod": aod,
            "aod_label": aod_label,
            "event_time": res.get("tb_event_time", ""),
            "event_name": res.get("display_event_name_cn", "")
        }
    except Exception as e:
        print(f"获取sunsetbot数据失败: {e}")
        return None


def photo_score(cloud, humidity, wind_speed, aqi, precip, sunsetbot_quality=0, event_type="set"):
    """
    风光摄影霞光评分算法（科学乘法模型）
    
    评分逻辑：基础分(SunsetBot) × 修饰系数(云量×湿度×风速×AQI)
    硬性否决：降水>2mm 或 SunsetBot不烧+云量极低 → 直接不建议
    
    参数：
        cloud: 云量百分比
        humidity: 湿度百分比
        wind_speed: 风速 km/h
        aqi: 空气质量指数
        precip: 降水量 mm
        sunsetbot_quality: SunsetBot鲜艳度(0-2)
        event_type: "rise"(朝霞)或"set"(晚霞)
    """
    score_details = []
    tips = []
    final_score = 0

    if precip > 2:
        level = "★★ 不建议前往"
        level_color = "#95A5A6"
        summary = "有降水，云层被冲刷，霞光概率极低"
        tips.append("🌧️ 有降水，不建议户外拍摄")
        return level, level_color, summary, tips

    if sunsetbot_quality < 0.1 and cloud < 10:
        level = "★★ 不建议前往"
        level_color = "#95A5A6"
        summary = "SunsetBot预测不烧且云量极低，无形成霞光的基础条件"
        tips.append("🌑 SunsetBot预测不烧，鲜艳度{:.3f}".format(sunsetbot_quality))
        tips.append("☁ 云量过少，无云层承接霞光")
        return level, level_color, summary, tips

    if sunsetbot_quality >= 1.0:
        base_score = 95
        score_details.append(f"🔥 基础分(SunsetBot大烧): {base_score}分")
        tips.append(f"🔥 SunsetBot预测大烧，鲜艳度{sunsetbot_quality}")
    elif sunsetbot_quality >= 0.8:
        base_score = 85
        score_details.append(f"🔥 基础分(SunsetBot中大烧): {base_score}分")
        tips.append(f"🔥 SunsetBot预测中大烧，鲜艳度{sunsetbot_quality}")
    elif sunsetbot_quality >= 0.5:
        base_score = 70
        score_details.append(f"🔥 基础分(SunsetBot中小烧): {base_score}分")
        tips.append(f"🔥 SunsetBot预测中小烧，鲜艳度{sunsetbot_quality}")
    elif sunsetbot_quality >= 0.3:
        base_score = 55
        score_details.append(f"🔥 基础分(SunsetBot微烧): {base_score}分")
        tips.append(f"🔥 SunsetBot预测微烧，鲜艳度{sunsetbot_quality}")
    elif sunsetbot_quality >= 0.1:
        base_score = 35
        score_details.append(f"🔥 基础分(SunsetBot弱烧): {base_score}分")
        tips.append(f"🔥 SunsetBot预测弱烧，鲜艳度{sunsetbot_quality}")
    else:
        base_score = 15
        score_details.append(f"🌑 基础分(SunsetBot不烧): {base_score}分")
        tips.append(f"🌑 SunsetBot预测不烧，鲜艳度{sunsetbot_quality}")

    if 20 <= cloud <= 60:
        cloud_factor = 1.2
        score_details.append(f"☁ 云量系数({cloud}%): ×{cloud_factor:.1f}")
        tips.append("云量适中，具备霞光形成的良好画布")
    elif 10 <= cloud < 20 or 60 < cloud <= 75:
        cloud_factor = 1.0
        score_details.append(f"☁ 云量系数({cloud}%): ×{cloud_factor:.1f}")
        tips.append("云量尚可，霞光层次一般")
    elif cloud < 10:
        cloud_factor = 0.6
        score_details.append(f"☁ 云量系数({cloud}%): ×{cloud_factor:.1f}")
        tips.append("云量偏少，缺少霞光载体")
    else:
        cloud_factor = 0.5
        score_details.append(f"☁ 云量系数({cloud}%): ×{cloud_factor:.1f}")
        tips.append("云量过多，可能遮挡阳光")

    if 60 <= humidity <= 80:
        humidity_factor = 1.1
        score_details.append(f"💧 湿度系数({humidity}%): ×{humidity_factor:.1f}")
        tips.append("空气湿度适宜，霞光饱和度高")
    elif 40 <= humidity < 60 or 80 < humidity <= 90:
        humidity_factor = 1.0
        score_details.append(f"💧 湿度系数({humidity}%): ×{humidity_factor:.1f}")
        tips.append("湿度一般，霞光通透度中等")
    else:
        humidity_factor = 0.8
        score_details.append(f"💧 湿度系数({humidity}%): ×{humidity_factor:.1f}")
        tips.append("湿度过低或过高，影响霞光效果")

    if wind_speed <= 5:
        wind_factor = 1.1
        score_details.append(f"🌬️ 风速系数({wind_speed}km/h): ×{wind_factor:.1f}")
        tips.append("微风环境，低空水汽稳定")
    elif 5 < wind_speed <= 10:
        wind_factor = 1.0
        score_details.append(f"🌬️ 风速系数({wind_speed}km/h): ×{wind_factor:.1f}")
        tips.append("风速适中，云层形态稳定")
    elif 10 < wind_speed <= 20:
        wind_factor = 0.85
        score_details.append(f"🌬️ 风速系数({wind_speed}km/h): ×{wind_factor:.1f}")
        tips.append("风速偏大，可能影响云层形态")
    else:
        wind_factor = 0.7
        score_details.append(f"🌬️ 风速系数({wind_speed}km/h): ×{wind_factor:.1f}")
        tips.append("风力较大，水汽易扩散")

    if aqi <= 50:
        aqi_factor = 1.0
        score_details.append(f"🌿 AQI系数({aqi}): ×{aqi_factor:.1f}")
        tips.append("空气质量优，画面通透干净")
    elif 50 < aqi <= 100:
        aqi_factor = 0.95
        score_details.append(f"🌿 AQI系数({aqi}): ×{aqi_factor:.1f}")
        tips.append("空气质量良，对画质影响较小")
    elif 100 < aqi <= 150:
        aqi_factor = 0.85
        score_details.append(f"🌿 AQI系数({aqi}): ×{aqi_factor:.1f}")
        tips.append("轻度污染，空气通透度下降")
    else:
        aqi_factor = 0.7
        score_details.append(f"🌿 AQI系数({aqi}): ×{aqi_factor:.1f}")
        tips.append("空气质量较差，影响画面通透度")

    if precip > 0:
        precip_factor = 0.7
        score_details.append(f"🌧️ 降水系数({precip}mm): ×{precip_factor:.1f}")
        tips.append("有微量降水，霞光概率降低")
    else:
        precip_factor = 1.0

    final_score = base_score * cloud_factor * humidity_factor * wind_factor * aqi_factor * precip_factor
    final_score = max(0, min(100, round(final_score)))

    score_details.append(f"📊 综合得分: {final_score}分")

    if final_score >= 80:
        level = "★★★★★ 绝佳拍摄日"
        level_color = "#FF6B6B"
        summary = "天时地利人和，大概率出现火烧云/绝美霞光，强烈建议前往"
    elif 60 <= final_score < 80:
        level = "★★★★ 推荐拍摄"
        level_color = "#FFB347"
        summary = "霞光条件不错，出片概率较高，值得前往"
    elif 40 <= final_score < 60:
        level = "★★★ 一般拍摄"
        level_color = "#4ECDC4"
        summary = "霞光条件普通，可随缘拍摄，建议观察实时天气"
    elif 20 <= final_score < 40:
        level = "★★ 不推荐"
        level_color = "#95A5A6"
        summary = "霞光概率较低，不建议专程前往"
    else:
        level = "★ 不建议"
        level_color = "#6B7280"
        summary = "气象条件不佳，大概率无明显霞光"

    return level, level_color, summary, tips


def push_wechat(title, content, topic=None):
    """推送消息到微信（支持PushPlus和BotTalk）"""
    if PUSH_METHOD == "bottalk" and BOTTALK_SENDKEY:
        return push_bottalk(title, content)
    return push_pushplus(title, content, topic)


def push_pushplus(title, content, topic=None):
    """通过PushPlus推送到微信"""
    url = "https://www.pushplus.plus/send"
    data = {
        "token": PUSHPLUS_TOKEN,
        "title": title,
        "content": content,
        "template": "html"
    }
    if topic:
        data["topic"] = topic
    headers = {"Content-Type": "application/json"}
    try:
        res = requests.post(url, json=data, headers=headers)
        return res.json()
    except Exception as e:
        print(f"PushPlus推送失败：{e}")
        return None


def push_bottalk(title, content):
    """通过BotTalk推送到微信（免费方案）"""
    import re
    text_content = re.sub(r'<[^>]*>', '', content)
    text_content = re.sub(r'\s+', ' ', text_content).strip()
    url = f"https://bot-talk.com/{BOTTALK_SENDKEY}.send"
    try:
        res = requests.post(url, data={
            "title": title,
            "desp": text_content
        }, timeout=10)
        try:
            return res.json()
        except:
            return {"result": res.text}
    except Exception as e:
        print(f"BotTalk推送失败：{e}")
        return None


def generate_city_report(city):
    """生成单个城市的预报HTML"""
    city_id = city["id"]
    city_name = city["name"]
    
    tomorrow = get_daily_weather(city_id, day_offset=1)
    if not tomorrow:
        return f'<div class="city-panel"><div class="card"><div class="summary">❌ {city_name}天气数据获取失败</div></div></div>', 0, 0

    aqi = get_air_quality(city_id)

    sunrise_hour = int(tomorrow["sunrise"].split(":")[0])
    sunset_hour = int(tomorrow["sunset"].split(":")[0])

    sunrise_hourly = get_hourly_weather(city_id, sunrise_hour) or {
        "cloud": tomorrow["cloud"],
        "humidity": tomorrow["humidity"],
        "wind_speed": tomorrow["wind_speed"],
        "precip": tomorrow["precip"],
        "text": tomorrow["text_day"]
    }
    sunset_hourly = get_hourly_weather(city_id, sunset_hour) or {
        "cloud": tomorrow["cloud"],
        "humidity": tomorrow["humidity"],
        "wind_speed": tomorrow["wind_speed"],
        "precip": tomorrow["precip"],
        "text": tomorrow["text_day"]
    }

    bot_name = city.get("bot_name", city_name)
    sunrise_bot = get_sunsetbot_data(bot_name, "rise_2")
    sunset_bot = get_sunsetbot_data(bot_name, "set_2")
    
    sr_quality = sunrise_bot["quality"] if sunrise_bot else 0
    ss_quality = sunset_bot["quality"] if sunset_bot else 0
    
    sr_level, sr_color, sr_summary, sr_tips = photo_score(
        sunrise_hourly["cloud"], sunrise_hourly["humidity"],
        sunrise_hourly["wind_speed"], aqi, sunrise_hourly["precip"], sr_quality
    )
    ss_level, ss_color, ss_summary, ss_tips = photo_score(
        sunset_hourly["cloud"], sunset_hourly["humidity"],
        sunset_hourly["wind_speed"], aqi, sunset_hourly["precip"], ss_quality
    )

    sr_status = sr_level.split(' ')[-1]
    ss_status = ss_level.split(' ')[-1]
    
    sr_border = 'red-box' if '绝佳' in sr_status else 'orange-box' if '推荐' in sr_status else 'green-box' if '一般' in sr_status else 'gray-box'
    ss_border = 'red-box' if '绝佳' in ss_status else 'orange-box' if '推荐' in ss_status else 'green-box' if '一般' in ss_status else 'gray-box'

    sr_bot_html = ""
    if sunrise_bot:
        sr_bot_html = f'''
        <div class="bot-box">
            <div class="bot-title">🔥 SunsetBot 专业数据</div>
            <table class="bot-table">
                <tr>
                    <td><div class="b-name">火烧云鲜艳度</div><div class="b-value">{sunrise_bot['quality']}</div><div class="b-label">{sunrise_bot['quality_label']}</div></td>
                    <td><div class="b-name">气溶胶(AOD)</div><div class="b-value">{sunrise_bot['aod']}</div><div class="b-label">{sunrise_bot['aod_label']}</div></td>
                </tr>
            </table>
        </div>
        '''
    
    ss_bot_html = ""
    if sunset_bot:
        ss_bot_html = f'''
        <div class="bot-box">
            <div class="bot-title">🔥 SunsetBot 专业数据</div>
            <table class="bot-table">
                <tr>
                    <td><div class="b-name">火烧云鲜艳度</div><div class="b-value">{sunset_bot['quality']}</div><div class="b-label">{sunset_bot['quality_label']}</div></td>
                    <td><div class="b-name">气溶胶(AOD)</div><div class="b-value">{sunset_bot['aod']}</div><div class="b-label">{sunset_bot['aod_label']}</div></td>
                </tr>
            </table>
        </div>
        '''
    
    sr_tips_html = '<div class="tip-list">' + ''.join([f'<div class="tip-item">{tip}</div>' for tip in sr_tips]) + '</div>'
    ss_tips_html = '<div class="tip-list">' + ''.join([f'<div class="tip-item">{tip}</div>' for tip in ss_tips]) + '</div>'

    city_html = f"""
        <div class="city-panel">
            <div class="city-header">
                <div class="city-title">📍 {city_name}</div>
                <div class="city-meta">天气 {tomorrow['text_day']} | {tomorrow['temp_min']}°~{tomorrow['temp_max']}° | AQI {aqi}</div>
            </div>

            <div class="card {sr_border}">
                <div class="card-header">
                    <div class="card-title">
                        <span class="icon">🌅</span>
                        <span>朝霞预报</span>
                    </div>
                    <span class="rating" style="background: {sr_color}15; color: {sr_color}; border: 1px solid {sr_color}30;">{sr_level}</span>
                </div>
                <div class="time-row">日出时间：{tomorrow['sunrise']}</div>
                <div class="summary">{sr_summary}</div>
                <table class="param-table">
                    <tr>
                        <td><div class="p-name">☁ 云量</div><div class="p-value">{sunrise_hourly['cloud']}<span class="p-unit">%</span></div></td>
                        <td><div class="p-name">💧 湿度</div><div class="p-value">{sunrise_hourly['humidity']}<span class="p-unit">%</span></div></td>
                        <td><div class="p-name">🌬️ 风速</div><div class="p-value">{sunrise_hourly['wind_speed']}<span class="p-unit">km/h</span></div></td>
                        <td><div class="p-name">🌧️ 降水</div><div class="p-value">{sunrise_hourly['precip']}<span class="p-unit">mm</span></div></td>
                    </tr>
                </table>
                {sr_bot_html}
                {sr_tips_html}
                <div class="note">⏰ 建议日出前30分钟抵达机位</div>
            </div>

            <div class="card {ss_border}">
                <div class="card-header">
                    <div class="card-title">
                        <span class="icon">🌇</span>
                        <span>晚霞预报</span>
                    </div>
                    <span class="rating" style="background: {ss_color}15; color: {ss_color}; border: 1px solid {ss_color}30;">{ss_level}</span>
                </div>
                <div class="time-row">日落时间：{tomorrow['sunset']}</div>
                <div class="summary">{ss_summary}</div>
                <table class="param-table">
                    <tr>
                        <td><div class="p-name">☁ 云量</div><div class="p-value">{sunset_hourly['cloud']}<span class="p-unit">%</span></div></td>
                        <td><div class="p-name">💧 湿度</div><div class="p-value">{sunset_hourly['humidity']}<span class="p-unit">%</span></div></td>
                        <td><div class="p-name">🌬️ 风速</div><div class="p-value">{sunset_hourly['wind_speed']}<span class="p-unit">km/h</span></div></td>
                        <td><div class="p-name">🌧️ 降水</div><div class="p-value">{sunset_hourly['precip']}<span class="p-unit">mm</span></div></td>
                    </tr>
                </table>
                {ss_bot_html}
                {ss_tips_html}
                <div class="note">⏰ 建议日落前40分钟抵达机位</div>
            </div>
        </div>
    """
    
    return city_html, sr_quality, ss_quality


def generate_daily_report():
    """生成多城市明日摄影预报（平铺展示，兼容微信）"""
    tomorrow_date = (datetime.now() + timedelta(days=1)).strftime('%Y年%m月%d日')
    week_day = ["日", "一", "二", "三", "四", "五", "六"][(datetime.now() + timedelta(days=1)).weekday()]

    cities_html = ""
    all_sr_quality = []
    all_ss_quality = []

    for i, city in enumerate(CITIES):
        city_html, sr_q, ss_q = generate_city_report(city)
        cities_html += city_html
        all_sr_quality.append(sr_q)
        all_ss_quality.append(ss_q)

    avg_sr_quality = sum(all_sr_quality) / len(all_sr_quality) if all_sr_quality else 0
    avg_ss_quality = sum(all_ss_quality) / len(all_ss_quality) if all_ss_quality else 0
    overall_score = (avg_sr_quality + avg_ss_quality) / 2
    
    if overall_score >= 0.5:
        overall_label = "🔥 值得期待"
        overall_color = "#FF6B6B"
    elif overall_score >= 0.2:
        overall_label = "✨ 可以观望"
        overall_color = "#FFB347"
    else:
        overall_label = "☁️ 今日休息"
        overall_color = "#6B7280"

    html_content = f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>风光摄影预报</title>
    <style>
        * {{ margin: 0; padding: 0; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'PingFang SC', 'Segoe UI', sans-serif; background: #f2f3f5; }}
        .page {{ max-width: 520px; margin: 0 auto; }}
        .header {{ background: linear-gradient(135deg, #FF6B6B 0%, #FFB347 50%, #FFE66D 100%); padding: 30px 20px; color: white; text-align: center; }}
        .header h1 {{ font-size: 24px; font-weight: 700; margin-bottom: 8px; }}
        .header .date {{ font-size: 14px; color: rgba(255,255,255,0.7); }}
        .overall {{ background: #fff; padding: 20px; margin: 15px; border-radius: 16px; text-align: center; box-shadow: 0 2px 10px rgba(0,0,0,0.05); }}
        .overall .label {{ font-size: 18px; font-weight: 600; color: {overall_color}; }}
        .overall .desc {{ font-size: 14px; color: #86909c; margin-top: 8px; }}
        .city-header {{ background: linear-gradient(90deg, #667eea 0%, #764ba2 100%); padding: 20px; margin: 15px; border-radius: 16px; color: white; }}
        .city-header .city-title {{ font-size: 20px; font-weight: 700; margin-bottom: 6px; }}
        .city-header .city-meta {{ font-size: 13px; opacity: 0.9; }}
        .city-divider {{ height: 20px; }}
        .card {{ background: #fff; margin: 0 15px 15px; border-radius: 16px; padding: 20px; box-shadow: 0 2px 10px rgba(0,0,0,0.05); }}
        .card-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }}
        .card-title {{ font-size: 18px; font-weight: 600; display: flex; align-items: center; gap: 8px; }}
        .card-title .icon {{ font-size: 24px; }}
        .rating {{ font-size: 14px; font-weight: 600; padding: 4px 14px; border-radius: 16px; }}
        .time-row {{ font-size: 13px; color: #86909c; margin-bottom: 16px; }}
        .summary {{ background: #f8fafc; padding: 14px; border-radius: 12px; font-size: 14px; color: #4f5660; line-height: 1.6; margin-bottom: 16px; }}
        .param-table {{ width: 100%; border-collapse: collapse; margin-bottom: 16px; }}
        .param-table td {{ padding: 10px 6px; background: #f8fafc; border-radius: 8px; text-align: center; }}
        .param-table .p-name {{ font-size: 12px; color: #86909c; }}
        .param-table .p-value {{ font-size: 16px; font-weight: 700; color: #1f2329; }}
        .param-table .p-unit {{ font-size: 11px; color: #86909c; }}
        .bot-box {{ background: #1a1a2e; padding: 16px; border-radius: 12px; margin-bottom: 16px; color: white; }}
        .bot-title {{ font-size: 12px; color: rgba(255,255,255,0.6); margin-bottom: 10px; }}
        .bot-table {{ width: 100%; border-collapse: collapse; }}
        .bot-table td {{ text-align: center; padding: 6px 0; width: 50%; }}
        .bot-table .b-name {{ font-size: 11px; color: rgba(255,255,255,0.5); }}
        .bot-table .b-value {{ font-size: 20px; font-weight: 700; }}
        .bot-table .b-label {{ font-size: 10px; color: rgba(255,255,255,0.4); }}
        .tip-list {{ margin-bottom: 16px; }}
        .tip-item {{ font-size: 13px; color: #4f5660; line-height: 1.6; padding: 4px 0; }}
        .note {{ background: #fff3cd; padding: 12px; border-radius: 8px; font-size: 12px; color: #856404; line-height: 1.5; }}
        .footer {{ padding: 20px; text-align: center; font-size: 11px; color: #a0a7b0; }}
        .red-box {{ border-left: 4px solid #FF6B6B; }}
        .orange-box {{ border-left: 4px solid #FFB347; }}
        .green-box {{ border-left: 4px solid #4ECDC4; }}
        .gray-box {{ border-left: 4px solid #95A5A6; }}
    </style>
</head>
<body>
    <div class="page">
        <div class="header">
            <h1>📸 明日摄影预报</h1>
            <div class="date">{tomorrow_date} · 星期{week_day}</div>
        </div>

        <div class="overall">
            <div class="label">{overall_label}</div>
            <div class="desc">共 {len(CITIES)} 个城市预报</div>
        </div>

        {cities_html}

        <div class="footer">PhotoWeather © 2026 · {datetime.now().strftime('%H:%M')}</div>
    </div>
</body>
</html>"""

    import random
    title = f"📸 {tomorrow_date} 风光摄影预报 {random.randint(100, 999)}"
    push_wechat(title, html_content, GROUP_TOPIC)
    print(f"{datetime.now()} 已推送明日完整预报")


schedule.every().day.at(DAILY_PUSH_TIME).do(generate_daily_report)


if __name__ == "__main__":
    print("风光摄影预报助手已启动，等待定时推送...")
    generate_daily_report()
    
    if os.getenv("CI") != "true":
        while True:
            schedule.run_pending()
            time.sleep(60)
