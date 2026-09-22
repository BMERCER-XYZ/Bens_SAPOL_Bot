import datetime
import json
import math
import os
import random
import re
import tempfile
import time
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import folium
import pytz
import requests
from bs4 import BeautifulSoup
from geopy.distance import geodesic
from geopy.geocoders import Nominatim

user_location = (-34.9206, 138.5210)
SAPOL_URL = "https://www.police.sa.gov.au/your-safety/road-safety/traffic-camera-locations"
tz = pytz.timezone("Australia/Adelaide")
ADELAIDE_CBD_COORDS = (-34.9285, 138.6007)
GREETING_TEMPLATE = "Good morning! :) Here are the speed camera locations for {today}:"


def _adelaide_today() -> str:
    return datetime.datetime.now(tz).strftime("%d/%m/%Y")


def fetch_with_playwright(url: str, timeout: int = 30, max_retries: int = 3) -> Optional[str]:
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        print("⚠️ Playwright is not installed.")
        return None
    for attempt in range(max_retries):
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                context = browser.new_context(user_agent=os.getenv("SAPOL_USER_AGENT", "Mozilla/5.0"))
                page = context.new_page()
                page.set_default_navigation_timeout(timeout * 1000)
                page.goto(url)
                try:
                    page.wait_for_load_state("networkidle", timeout=5000)
                except Exception:
                    pass
                html = page.content()
                browser.close()
            if "Just a moment" not in html and "cf-browser-verification" not in html:
                return html
            print(f"⚠️ Cloudflare challenge detected (attempt {attempt + 1}); retrying")
            time.sleep(2 + random.random() * 2)
        except Exception as error:
            print(f"⚠️ Playwright fetch failed (attempt {attempt + 1}): {error}")
    return None


def get_region(lat: float, lon: float) -> str:
    if geodesic(ADELAIDE_CBD_COORDS, (lat, lon)).km < 2.5:
        return "CBD"
    angle = math.degrees(math.atan2(lat - ADELAIDE_CBD_COORDS[0], lon - ADELAIDE_CBD_COORDS[1]))
    if 45 <= angle < 135:
        return "Northern Suburbs"
    if -45 <= angle < 45:
        return "Eastern Suburbs"
    if -135 <= angle < -45:
        return "Southern Suburbs"
    return "Western Suburbs"


def generate_map_image(cameras: List[Dict[str, Any]]) -> Optional[str]:
    if not cameras or not os.getenv("API_KEY"):
        return None
    try:
        api_key = quote(os.environ["API_KEY"], safe="")
        map_view = folium.Map(zoom_control=False)
        folium.TileLayer(
            tiles=f"https://{{s}}.basemaps.cartocdn.com/dark_all/{{z}}/{{x}}/{{y}}{{r}}.png?key={api_key}",
            attr="&copy; OpenStreetMap contributors &copy; CARTO",
            subdomains="abcd",
            max_zoom=20,
        ).add_to(map_view)
        for camera in cameras:
            if camera.get("geojson"):
                folium.GeoJson(camera["geojson"], style_function=lambda _: {"color": "#FF0000", "weight": 5}, tooltip=camera["name"]).add_to(map_view)
            elif camera.get("lat") is not None:
                folium.Circle([camera["lat"], camera["lon"]], radius=200, color="#FF3333", fill=True, fill_color="#FF3333", tooltip=camera["name"]).add_to(map_view)
        lat_max = geodesic(kilometers=5).destination(ADELAIDE_CBD_COORDS, 0).latitude
        lat_min = geodesic(kilometers=5).destination(ADELAIDE_CBD_COORDS, 180).latitude
        lon_max = geodesic(kilometers=5).destination(ADELAIDE_CBD_COORDS, 90).longitude
        lon_min = geodesic(kilometers=5).destination(ADELAIDE_CBD_COORDS, 270).longitude
        map_view.fit_bounds([[lat_min, lon_min], [lat_max, lon_max]])
        with tempfile.NamedTemporaryFile(suffix=".html", delete=False, mode="w", encoding="utf-8") as html_file:
            map_view.save(html_file.name)
            html_path = html_file.name
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as image_file:
            image_path = image_file.name
        from playwright.sync_api import sync_playwright
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 800, "height": 600})
            page.goto(f"file://{html_path}")
            time.sleep(2)
            page.screenshot(path=image_path)
            browser.close()
        os.remove(html_path)
        return image_path
    except Exception as error:
        print(f"⚠️ Map generation failed: {error}")
        return None


def _normalise_date(value: str) -> Optional[str]:
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d %B %Y", "%d %b %Y"):
        try:
            return datetime.datetime.strptime(value.strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return None


def _fetch_camera_names_by_date() -> Dict[str, List[str]]:
    html = fetch_with_playwright(SAPOL_URL)
    if not html:
        return {}
    cams_by_date: Dict[str, List[str]] = {}
    date_pattern = re.compile(r"^(\d{1,2}/\d{1,2}/\d{4}|\d{4}-\d{2}-\d{2}|\d{1,2} [A-Za-z]+ \d{4})\s*[-–—:,]?\s*(.+)$")
    for li in BeautifulSoup(html, "html.parser").find_all("li"):
        data_value = li.get("data-value")
        text = li.get_text(" ", strip=True)
        date_value = _normalise_date(data_value or "")
        name = text[len(data_value):].lstrip(" -–—:,\t") if data_value and text.startswith(data_value) else text
        if not date_value:
            match = date_pattern.match(text)
            if match:
                date_value, name = _normalise_date(match.group(1)), match.group(2)
        if date_value and name:
            cams_by_date.setdefault(date_value, []).append(name.strip())
    return cams_by_date


def _geocode_names(names: List[str]) -> List[Dict[str, Any]]:
    geolocator = Nominatim(user_agent="sapol_bot")
    results = []
    seen = set()
    for name in names:
        if name in seen:
            continue
        seen.add(name)
        camera: Dict[str, Any] = {"name": name, "lat": None, "lon": None, "region": "Unknown"}
        try:
            location = geolocator.geocode(f"{name}, South Australia", timeout=10, geometry="geojson")
            if location:
                camera.update({"lat": location.latitude, "lon": location.longitude, "region": get_region(location.latitude, location.longitude), "distance": geodesic(user_location, (location.latitude, location.longitude)).km, "geojson": location.raw.get("geojson")})
        except Exception as error:
            print(f"⚠️ Geocoding failed for {name}: {error}")
        results.append(camera)
        time.sleep(1)
    return results


def get_camera_schedule() -> Dict[str, List[Dict[str, Any]]]:
    names_by_date = _fetch_camera_names_by_date()
    return {date: _geocode_names(names) for date, names in names_by_date.items()}


def _select_schedule_date(schedule: Dict[str, List[Dict[str, Any]]]) -> Optional[str]:
    if not schedule:
        return None
    today = datetime.datetime.now(tz).date()
    dates = sorted(datetime.date.fromisoformat(date) for date in schedule)
    return next((date for date in dates if date >= today), dates[-1]).isoformat()


def get_metropolitan_today(schedule: Dict[str, List[Dict[str, Any]]]):
    chosen_date = _select_schedule_date(schedule)
    if not chosen_date:
        return [], _adelaide_today()
    cameras = schedule[chosen_date]
    cameras.sort(key=lambda camera: camera.get("distance", float("inf")))
    return cameras, datetime.date.fromisoformat(chosen_date).strftime("%d/%m/%Y")


def _read_fixed_cameras() -> List[Dict[str, Any]]:
    path = os.path.join(os.path.dirname(__file__), "Fixed_Cameras.txt")
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as camera_file:
        lines = [line.strip() for line in camera_file if line.strip()]
    return [{"name": lines[index], "type": lines[index + 1]} for index in range(0, len(lines) - 1, 2)]


def write_site_data(schedule: Dict[str, List[Dict[str, Any]]]) -> None:
    fixed = _read_fixed_cameras()
    locations = {camera["name"]: camera for camera in _geocode_names([camera["name"] for camera in fixed])}
    for camera in fixed:
        camera.update({key: value for key, value in locations.get(camera["name"], {}).items() if key != "name"})
    all_cameras = {camera["name"]: camera for cameras in schedule.values() for camera in cameras}
    os.makedirs("docs", exist_ok=True)
    with open("docs/data.json", "w", encoding="utf-8") as data_file:
        json.dump({
            "generated_at": datetime.datetime.now(tz).isoformat(),
            "tile_key": os.getenv("API_KEY", ""),
            "dates": schedule,
            "all_cameras": list(all_cameras.values()),
            "fixed_cameras": fixed,
        }, data_file, ensure_ascii=True)


def send_to_discord(cameras, image_path: Optional[str] = None, date_str: Optional[str] = None):
    webhook = os.getenv("DISCORD_WEBHOOK")
    if not webhook:
        print("❌ Missing DISCORD_WEBHOOK environment variable.")
        return
    date_for_message = date_str or _adelaide_today()
    map_url = os.getenv("MAP_URL", "https://bmercer-xyz.github.io/Bens_SAPOL_Bot/")
    if not cameras:
        message = f"No metropolitan cameras found for {date_for_message}.\n\n[Open interactive map]({map_url})"
        requests.post(webhook, json={"content": message})
        return
    message = f"**{GREETING_TEMPLATE.format(today=date_for_message)}**\n"
    for camera in cameras:
        distance = camera.get("distance")
        message += f"• {camera['name']} — `{distance:.1f} km`\n" if distance is not None else f"• {camera['name']} — `distance unknown`\n"
    message += f"\n[Open interactive map]({map_url})"
    files = {}
    opened_file = None
    if image_path and os.path.exists(image_path):
        opened_file = open(image_path, "rb")
        files["file"] = ("map_preview.png", opened_file, "image/png")
    try:
        if len(message) > 2000:
            for part in [message[index:index + 1900] for index in range(0, len(message), 1900)]:
                requests.post(webhook, json={"content": part})
            if files:
                requests.post(webhook, files=files)
        else:
            response = requests.post(webhook, data={"content": message}, files=files)
            print("✅ Message sent successfully." if response.status_code in (200, 204) else f"❌ Discord status: {response.status_code}")
    finally:
        if opened_file:
            opened_file.close()


if __name__ == "__main__":
    schedule = get_camera_schedule()
    write_site_data(schedule)
    cameras, used_date = get_metropolitan_today(schedule)
    map_image = generate_map_image(cameras)
    send_to_discord(cameras, map_image, date_str=used_date)
    if map_image and os.path.exists(map_image):
        os.remove(map_image)