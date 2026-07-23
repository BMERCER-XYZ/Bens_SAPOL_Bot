# Import required libraries
import requests
import math
import random
from bs4 import BeautifulSoup
from geopy.distance import geodesic
from geopy.geocoders import Nominatim
import datetime
import pytz
import os
import time
import folium
import tempfile
from typing import Optional, List, Dict, Any

# Set your location (example: Lockleys, SA)
user_location = (-34.9206, 138.5210)

# URL of SAPOL traffic camera listings
SAPOL_URL = "https://www.police.sa.gov.au/your-safety/road-safety/traffic-camera-locations"

# Set timezone to Adelaide (used when computing dates dynamically)
tz = pytz.timezone("Australia/Adelaide")

# helper to format current date in DD/MM/YYYY for our lookup/greetings
def _adelaide_today() -> str:
    return datetime.datetime.now(tz).strftime("%d/%m/%Y")

# Adelaide CBD Coordinates for region calculation
ADELAIDE_CBD_COORDS = (-34.9285, 138.6007)

GREETING_TEMPLATE = "Good morning! :) Here are the speed camera locations for {today}:"


def fetch_with_playwright(url: str, timeout: int = 30, max_retries: int = 3) -> Optional[str]:
    """Use Playwright to render the page and return HTML. Returns None on failure.

    This is used as a fallback when direct requests are blocked (e.g., 403) or
    when Cloudflare presents an interstitial.  We perform a few retries with a
    short delay if we detect the "Just a moment" challenge string in the
    returned HTML.
    """
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        print("⚠️ Playwright is not installed. Install 'playwright' and run 'playwright install' to enable browser fallback.")
        return None

    attempt = 0
    html = None
    while attempt < max_retries:
        attempt += 1
        try:
            with sync_playwright() as p:
                # running headless should normally be fine but cloudflare sometimes
                # treats headless browsers differently; the user agent is also
                # randomized via environment variable to help.
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(user_agent=os.getenv(
                    "SAPOL_USER_AGENT",
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                ))
                page = context.new_page()
                page.set_default_navigation_timeout(timeout * 1000)
                page.goto(url)
                # Wait for some page content to load; networkidle is best effort
                try:
                    page.wait_for_load_state("networkidle", timeout=5000)
                except Exception:
                    pass
                html = page.content()
                browser.close()
        except Exception as e:
            print(f"⚠️ Playwright fetch failed (attempt {attempt}): {e}")
            html = None

        # detect Cloudflare interstitial pages by looking for tell‑tale strings
        if html and ("Just a moment" in html or "cf-browser-verification" in html):
            print(f"⚠️ Cloudflare challenge detected (attempt {attempt}); retrying")
            # shave off a little jitter so we don't look automated
            time.sleep(2 + random.random() * 2)
            continue

        # if we got some HTML and it doesn't look like a challenge page, return it
        return html

    # exhausted retries, give back whatever we have (may be None or a challenge page)
    return html

def generate_map_image(cameras: List[Dict[str, Any]]) -> Optional[str]:
    """Generates a static map image of camera locations using Folium and Playwright."""
    if not cameras:
        return None

    print("🗺️ Generating map preview...")
    try:
        # Initialize map
        m = folium.Map(zoom_control=False)
        folium.TileLayer(
            tiles="CartoDB dark_matter",
        ).add_to(m)

        for cam in cameras:
            if cam.get('geojson'):
                # If we have GeoJSON (likely a LineString for a road), plot it
                folium.GeoJson(
                    cam['geojson'],
                    style_function=lambda x: {
                        'color': '#FF0000',
                        'weight': 5,
                        'opacity': 0.7
                    },
                    tooltip=cam['name']
                ).add_to(m)
            elif cam.get('lat') is not None:
                # Fallback to circle if no geometry or Point geometry
                folium.Circle(
                    location=[cam['lat'], cam['lon']],
                    radius=200,
                    color="#FF3333",
                    fill=True,
                    fill_color="#FF3333",
                    fill_opacity=0.4,
                    tooltip=cam['name']
                ).add_to(m)
        
        # Set fixed bounds: 5km radius box around CBD
        # Calculate bounds (0=North, 180=South, 90=East, 270=West)
        lat_max = geodesic(kilometers=5).destination(ADELAIDE_CBD_COORDS, 0).latitude
        lat_min = geodesic(kilometers=5).destination(ADELAIDE_CBD_COORDS, 180).latitude
        lon_max = geodesic(kilometers=5).destination(ADELAIDE_CBD_COORDS, 90).longitude
        lon_min = geodesic(kilometers=5).destination(ADELAIDE_CBD_COORDS, 270).longitude
        
        m.fit_bounds([[lat_min, lon_min], [lat_max, lon_max]])
        
        # Save map to a temporary HTML file
        with tempfile.NamedTemporaryFile(suffix=".html", delete=False, mode='w', encoding='utf-8') as tmp_html:
            m.save(tmp_html.name)
            tmp_html_path = tmp_html.name

        # Use Playwright to screenshot the local HTML file
        from playwright.sync_api import sync_playwright
        
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp_img:
            output_image_path = tmp_img.name

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 800, "height": 600})
            page.goto(f"file://{tmp_html_path}")
            # Wait a moment for tiles to load
            time.sleep(2)
            page.screenshot(path=output_image_path)
            browser.close()

        # Cleanup HTML
        os.remove(tmp_html_path)
        
        return output_image_path

    except Exception as e:
        print(f"⚠️ Map generation failed: {e}")
        return None

def get_region(lat: float, lon: float) -> str:
    """Determine the region (North, East, South, West, CBD) based on coordinates."""
    cbd_dist = geodesic(ADELAIDE_CBD_COORDS, (lat, lon)).km
    
    if cbd_dist < 2.5:
        return "CBD"

    # Calculate bearing to determine N/E/S/W
    dy = lat - ADELAIDE_CBD_COORDS[0]
    dx = lon - ADELAIDE_CBD_COORDS[1]
    angle = math.degrees(math.atan2(dy, dx))

    # Angle is standard math angle (0 is East, 90 is North, etc.)
    if 45 <= angle < 135:
        return "Northern Suburbs"
    elif -45 <= angle < 45:
        return "Eastern Suburbs"
    elif -135 <= angle < -45:
        return "Southern Suburbs"
    else:
        return "Western Suburbs"

def get_metropolitan_today():
    """Fetch and parse SAPOL camera list, preferring today's entries but
    falling back to the nearest scheduled date if necessary.

    Returns a tuple `(camera_list, date_used_string)` where `date_used_string`
    is the calendar date that was actually matched (e.g. "22/02/2026").
    """
    # recalc today so repeated runs use an up-to-date value
    today = _adelaide_today()
    print(f"📅 Fetching cameras for: {today}")

    html = fetch_with_playwright(SAPOL_URL)
    if not html:
        print("❌ Failed to fetch page using Playwright.")
        return [], today

    # if our helper returned a Cloudflare challenge page despite retries, try one
    # more time with a pause.  This is just a belt‑and‑braces check.
    if html and ("Just a moment" in html or "cf-browser-verification" in html):
        print("⚠️ Received Cloudflare interstitial; sleeping and retrying once more")
        time.sleep(5)
        html = fetch_with_playwright(SAPOL_URL)
        if not html or "Just a moment" in html or "cf-browser-verification" in html:
            print("❌ Still seeing Cloudflare challenge after retry, aborting.")
            snippet = html[:2000].replace('\n', ' ') if html else ''
            print("Page snippet:", snippet[:1000])
            return [], today

    soup = BeautifulSoup(html, "html.parser")

    # collect all list items that look like camera entries
    cams_by_date = {}

    def _record(li, date_str, name):
        cams_by_date.setdefault(date_str, []).append(name)

    # helper to try strip a date prefix from text
    def _strip_date_prefix(text, date_str):
        if text.startswith(date_str):
            # remove any punctuation or whitespace that follows
            return text[len(date_str):].lstrip(' -–—:,\t')
        return text

    for li in soup.find_all("li"):
        dv = li.get("data-value")
        text = li.get_text(" ", strip=True)
        if dv:
            name = _strip_date_prefix(text, dv).strip()
            if name:
                _record(li, dv, name)
            continue
        # if there's no data-value, try to guess a date at the start of text
        parts = text.split(None, 1)
        if len(parts) > 1 and any(parts[0] == fmt for fmt in [today,
                                                               datetime.datetime.now(tz).strftime("%Y-%m-%d"),
                                                               datetime.datetime.now(tz).strftime("%d %B %Y"),
                                                               datetime.datetime.now(tz).strftime("%d %b %Y")]):
            # first token looks like one of our date formats
            date_str = parts[0]
            name = parts[1]
            _record(li, date_str, name)
            continue
        # otherwise skip this <li> - probably part of navigation/menu

    if not cams_by_date:
        print("❌ No camera entries could be parsed from page.")
        snippet = html[:2000].replace('\n', ' ') if html else ''
        print("Page snippet:", snippet[:1000])
        return [], today

    # try to use today's list first
    if today in cams_by_date:
        chosen_date = today
    else:
        # parse all date strings into datetimes for comparison
        parsed = []
        for ds in cams_by_date.keys():
            for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d %B %Y", "%d %b %Y"):
                try:
                    dt = datetime.datetime.strptime(ds, fmt)
                    parsed.append((dt, ds))
                    break
                except Exception:
                    continue
        if not parsed:
            # nothing parsed? just pick arbitrary key
            chosen_date = next(iter(cams_by_date))
        else:
            now_dt = datetime.datetime.now(tz).replace(tzinfo=None)
            # pick the smallest date >= today, otherwise the latest past date
            future = [p for p in parsed if p[0].date() >= now_dt.date()]
            if future:
                chosen_date = min(future)[1]
            else:
                chosen_date = max(parsed)[1]
        print(f"⚠️ No cameras for today ({today}); using date {chosen_date} from page.")

    raw_cameras = cams_by_date.get(chosen_date, [])
    if not raw_cameras:
        print(f"❌ After fallback no cameras found for {chosen_date}.")
        return [], chosen_date

    # Remove duplicate camera entries while preserving order
    seen = set()
    unique_cameras = []
    for cam in raw_cameras:
        if cam not in seen:
            seen.add(cam)
            unique_cameras.append(cam)
    
    raw_cameras = unique_cameras
    if len(unique_cameras) < len(cams_by_date.get(chosen_date, [])):
        print(f"🔄 Removed {len(cams_by_date.get(chosen_date, [])) - len(unique_cameras)} duplicate camera entries.")

    # Geocode each camera location and calculate distance from user's location
    geolocator = Nominatim(user_agent="sapol_bot")
    camera_list = []

    for cam in raw_cameras:
        try:
            # Request geojson geometry to highlight roads
            location = geolocator.geocode(f"{cam}, South Australia", timeout=10, geometry='geojson')
            if location:
                cam_coords = (location.latitude, location.longitude)
                distance_km = geodesic(user_location, cam_coords).km
                region = get_region(location.latitude, location.longitude)
                camera_list.append({
                    "name": cam,
                    "distance": distance_km,
                    "region": region,
                    "lat": location.latitude,
                    "lon": location.longitude,
                    "geojson": location.raw.get("geojson")
                })
            else:
                camera_list.append({
                    "name": cam,
                    "distance": None,
                    "region": "Unknown",
                    "lat": None,
                    "lon": None,
                    "geojson": None
                })
        except Exception as e:
            print(f"⚠️ Geocoding failed for {cam}: {e}")
            camera_list.append({
                "name": cam,
                "distance": None,
                "region": "Unknown",
                "lat": None,
                "lon": None,
                "geojson": None
            })
        
        # Sleep to respect Nominatim’s rate limit
        time.sleep(1)

    # Sort cameras by distance (unknown distances go to the end)
    camera_list.sort(key=lambda x: x["distance"] if x["distance"] is not None else float("inf"))
    return camera_list, chosen_date

def send_to_discord(cameras, image_path: Optional[str] = None, date_str: Optional[str] = None):
    # Send the formatted camera list to a Discord webhook
    webhook = os.getenv("DISCORD_WEBHOOK")
    if not webhook:
        print("❌ Missing DISCORD_WEBHOOK environment variable.")
        return

    # use provided date or recalc current
    date_for_message = date_str or _adelaide_today()

    if not cameras:
        message = f"No metropolitan cameras found for {date_for_message}."
        requests.post(webhook, json={"content": message})
        return

    # Build the message
    greeting = GREETING_TEMPLATE.format(today=date_for_message)
    message = f"**{greeting}**\n"
    
    for cam in cameras:
        dist = cam['distance']
        name = cam['name']
        if dist is not None:
            message += f"• {name} — `{dist:.1f} km`\n"
        else:
            message += f"• {name} — `distance unknown`\n"

    # Send message to Discord via POST request
    # Check message length limit (Discord is 2000 chars)
    # Note: If sending an image, we need to use multipart/form-data, which requests handles via 'files'
    # and the JSON payload becomes 'payload_json' string if using files, or just data.
    # But for simple webhooks, 'content' field in body with files often works if structured right.
    # Best practice for Discord webhooks with files is:
    # files = {'file': open(image_path, 'rb')}
    # data = {'content': message}
    
    files = {}
    opened_file = None
    if image_path and os.path.exists(image_path):
        opened_file = open(image_path, 'rb')
        files['file'] = ('map_preview.png', opened_file, 'image/png')

    try:
        if len(message) > 2000:
            # If message is too long, we can't easily attach the file to all split parts.
            # Strategy: Send the image with the first part, or send text first then image.
            # Let's send text parts first, then image separately if needed.
            parts = [message[i:i+1900] for i in range(0, len(message), 1900)]
            for i, part in enumerate(parts):
                # Attach file only to the last part? Or send file separately?
                # Sending file separately is safer.
                requests.post(webhook, json={"content": part})
            
            if files:
                requests.post(webhook, files=files)
        else:
            response = requests.post(webhook, data={"content": message}, files=files)
            if response.status_code not in (200, 204):
                print(f"❌ Failed to send message to Discord. Status code: {response.status_code}")
            else:
                print("✅ Message sent successfully.")
    finally:
        if opened_file:
            opened_file.close()

# Main execution block: fetch today's cameras and send to Discord
if __name__ == "__main__":
    cameras, used_date = get_metropolitan_today()
    
    # Generate map if we have cameras
    map_image = None
    if cameras:
        map_image = generate_map_image(cameras)
        
    send_to_discord(cameras, map_image, date_str=used_date)
    
    # Clean up
    if map_image and os.path.exists(map_image):
        try:
            os.remove(map_image)
        except Exception:
            pass
