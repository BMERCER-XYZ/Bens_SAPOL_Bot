import datetime
import json
import math
import os
import re
import tempfile
import time
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import folium
import pytz
import requests
from bs4 import BeautifulSoup
from geopy.distance import geodesic
from geopy.geocoders import Nominatim

user_location = (-34.9206, 138.5210)
RSS_URL = "https://speedcameras.com.au/feed/"
tz = pytz.timezone("Australia/Adelaide")
ADELAIDE_CBD_COORDS = (-34.9285, 138.6007)
GREETING_TEMPLATE = "Good morning! :) Here are the speed camera locations for {today}:"
SA_BOUNDS = ((-38.2, 129.0), (-25.9, 141.5))
CAMERA_RETENTION_DAYS = 5


def _adelaide_today() -> str:
    return datetime.datetime.now(tz).strftime("%d/%m/%Y")


def _in_south_australia(lat: float, lon: float) -> bool:
    (south, west), (north, east) = SA_BOUNDS
    return south <= lat <= north and west <= lon <= east


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
    cleaned = re.sub(r"\b(\d{1,2})(st|nd|rd|th)\b", r"\1", value.strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r"^[A-Za-z]+,\s*", "", cleaned)
    for fmt in (
        "%d/%m/%Y",
        "%Y-%m-%d",
        "%d %B %Y",
        "%d %b %Y",
        "%A %d %B %Y",
        "%a %d %B %Y",
        "%A %d %b %Y",
        "%a %d %b %Y",
    ):
        try:
            return datetime.datetime.strptime(cleaned, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return None


def _nearest_section_date(tag: Any, fallback_date: str) -> str:
    for previous in tag.find_all_previous(["h1", "h2", "h3", "h4", "h5", "h6", "p", "strong", "b"]):
        parsed = _normalise_date(previous.get_text(" ", strip=True))
        if parsed:
            return parsed
    return fallback_date


def _fetch_camera_names_by_date() -> Dict[str, List[str]]:
    try:
        response = requests.get(RSS_URL, timeout=30)
        response.raise_for_status()
        feed = ET.fromstring(response.content)
    except (requests.RequestException, ET.ParseError) as error:
        print(f"⚠️ RSS feed fetch failed: {error}")
        return {}

    cams_by_date: Dict[str, List[str]] = {}
    content_namespace = "{http://purl.org/rss/1.0/modules/content/}encoded"
    for item in feed.findall("./channel/item"):
        link = item.findtext("link", default="")
        date_match = re.search(r"speed-cameras-(\d{8})", link)
        date_value = None
        if date_match:
            date_value = datetime.datetime.strptime(date_match.group(1), "%Y%m%d").strftime("%Y-%m-%d")
        if not date_value:
            description = item.findtext("description", default="")
            date_match = re.search(r"\b\d{1,2} [A-Za-z]+ \d{4}\b", description)
            date_value = _normalise_date(date_match.group(0)) if date_match else None

        encoded_content = item.findtext(content_namespace, default="")
        if not date_value or not encoded_content:
            continue
        soup = BeautifulSoup(encoded_content, "html.parser")
        for li in soup.find_all("li"):
            name = re.sub(r"\s*\([^)]*\)\s*$", "", li.get_text(" ", strip=True)).strip()
            if name:
                entry_date = _nearest_section_date(li, date_value)
                cams_by_date.setdefault(entry_date, []).append(name)
    return cams_by_date


def _apply_retention_window(schedule: Dict[str, List[Dict[str, Any]]], retention_days: int = CAMERA_RETENTION_DAYS) -> Dict[str, List[Dict[str, Any]]]:
    cutoff_date = datetime.datetime.now(tz).date() - datetime.timedelta(days=retention_days - 1)
    return {
        date: cameras
        for date, cameras in schedule.items()
        if datetime.date.fromisoformat(date) >= cutoff_date
    }


def _geocode_names(names: List[str]) -> List[Dict[str, Any]]:
    geolocator = Nominatim(user_agent="sapol_bot")
    results = []
    seen = set()
    for name in names:
        name = re.sub(r"\s+", " ", name.replace("\u00a0", " ")).strip()
        if name in seen:
            continue
        seen.add(name)
        camera: Dict[str, Any] = {"name": name, "lat": None, "lon": None, "region": "Unknown"}
        try:
            parts = [part.strip() for part in name.split(",", 1)]
            road = parts[0]
            suburb = parts[1] if len(parts) > 1 else ""
            road_queries = [road]
            if "/" in road:
                road_queries.insert(0, road.replace("/", " & "))
            if " TO " in suburb.upper():
                suburb_queries = [suburb.split(" TO ", 1)[0], suburb.split(" TO ", 1)[1]]
            else:
                suburb_queries = [suburb]
            queries = [
                f"{road_query}, {suburb_query}, South Australia"
                for road_query in road_queries
                for suburb_query in suburb_queries
                if suburb_query
            ]
            queries.append(f"{name}, South Australia")
            location = None
            for query in queries:
                try:
                    candidate = geolocator.geocode(
                        query,
                        timeout=10,
                        geometry="geojson",
                        country_codes="au",
                        viewbox=SA_BOUNDS,
                        bounded=True,
                    )
                except Exception:
                    break
                if candidate and _in_south_australia(candidate.latitude, candidate.longitude):
                    location = candidate
                    break
            if location:
                camera.update({"lat": location.latitude, "lon": location.longitude, "region": get_region(location.latitude, location.longitude), "distance": geodesic(user_location, (location.latitude, location.longitude)).km, "geojson": location.raw.get("geojson")})
            else:
                photon_response = requests.get(
                    "https://photon.komoot.io/api/",
                    params={"q": f"{name}, South Australia, Australia", "limit": 5, "bbox": "129,-38.2,141.5,-25.9"},
                    headers={"User-Agent": "sapol_bot"},
                    timeout=10,
                )
                photon_response.raise_for_status()
                features = photon_response.json().get("features", [])
                valid_features = [
                    feature for feature in features
                    if feature.get("geometry", {}).get("type") == "Point"
                    and _in_south_australia(*reversed(feature["geometry"]["coordinates"]))
                ]
                if valid_features:
                    coordinates = valid_features[0]["geometry"]["coordinates"]
                    latitude, longitude = coordinates[1], coordinates[0]
                    camera.update({"lat": latitude, "lon": longitude, "region": get_region(latitude, longitude), "distance": geodesic(user_location, (latitude, longitude)).km, "geojson": {"type": "Point", "coordinates": coordinates}})
        except Exception as error:
            print(f"⚠️ Geocoding failed for {name}: {error}")
        results.append(camera)
        time.sleep(1)
    return results


def get_camera_schedule() -> Dict[str, List[Dict[str, Any]]]:
    names_by_date = _fetch_camera_names_by_date()
    schedule = {date: _geocode_names(names) for date, names in names_by_date.items()}
    return _apply_retention_window(schedule)


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
        lines = [re.sub(r"\s+", " ", line.replace("\u00a0", " ")).strip() for line in camera_file if line.strip()]
    cameras = []
    index = 0
    while index < len(lines):
        if lines[index].lower() == "decommissioned cameras":
            index += 1
            continue
        if index + 3 >= len(lines):
            break
        longitude = re.fullmatch(r"Longitude:\s*(-?\d+(?:\.\d+)?)", lines[index + 2], re.IGNORECASE)
        latitude = re.fullmatch(r"Latitude:\s*(-?\d+(?:\.\d+)?)", lines[index + 3], re.IGNORECASE)
        if not longitude or not latitude:
            index += 1
            continue
        cameras.append({
            "name": lines[index],
            "type": lines[index + 1],
            "lon": float(longitude.group(1)),
            "lat": float(latitude.group(1)),
        })
        index += 4
    return cameras


def write_site_data(schedule: Dict[str, List[Dict[str, Any]]]) -> None:
    fixed = _read_fixed_cameras()
    for camera in fixed:
        camera.update({
            "region": get_region(camera["lat"], camera["lon"]),
            "distance": geodesic(user_location, (camera["lat"], camera["lon"])).km,
            "geojson": {"type": "Point", "coordinates": [camera["lon"], camera["lat"]]},
        })
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
        message = f"No metropolitan cameras found for {date_for_message}.\n\n{map_url}"
        requests.post(webhook, json={"content": message})
        return
    message = f"**{GREETING_TEMPLATE.format(today=date_for_message)}**\n"
    for camera in cameras:
        distance = camera.get("distance")
        message += f"• {camera['name']} — `{distance:.1f} km`\n" if distance is not None else f"• {camera['name']} — `distance unknown`\n"
    message += f"\n{map_url}"
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