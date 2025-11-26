# Import required libraries
import requests
from bs4 import BeautifulSoup
from geopy.distance import geodesic
from geopy.geocoders import Nominatim
import datetime
import pytz
import os
import time
from typing import Optional

# Set your location (example: Lockleys, SA)
user_location = (-34.9206, 138.5210)

# URL of SAPOL traffic camera listings
SAPOL_URL = "https://www.police.sa.gov.au/your-safety/road-safety/traffic-camera-locations"

# Set timezone to Adelaide and get today’s date in DD/MM/YYYY format
tz = pytz.timezone("Australia/Adelaide")
today = datetime.datetime.now(tz).strftime("%d/%m/%Y")


def fetch_with_playwright(url: str, timeout: int = 30) -> Optional[str]:
    """Use Playwright to render the page and return HTML. Returns None on failure.

    This is used as a fallback when direct requests are blocked (e.g., 403).
    """
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        print("⚠️ Playwright is not installed. Install 'playwright' and run 'playwright install' to enable browser fallback.")
        return None

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(user_agent=os.getenv("SAPOL_USER_AGENT", "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"))
            page = context.new_page()
            page.set_default_navigation_timeout(timeout * 1000)
            page.goto(url)
            # Wait for some page content to load; adjust selector if the site uses dynamic loading
            try:
                page.wait_for_load_state("networkidle", timeout=5000)
            except Exception:
                pass
            html = page.content()
            browser.close()
            return html
    except Exception as e:
        print(f"⚠️ Playwright fetch failed: {e}")
        return None

def get_metropolitan_today():
    # Fetch and parse SAPOL camera list for today's metropolitan locations
    print(f"📅 Fetching cameras for: {today}")

    # Use a session with a browser-like User-Agent to avoid bot blocking (403)
    session = requests.Session()
    session.headers.update({
        "User-Agent": os.getenv("SAPOL_USER_AGENT", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                                           "AppleWebKit/537.36 (KHTML, like Gecko) "
                                           "Chrome/120.0.0.0 Safari/537.36"),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Referer": "https://www.google.com/",
    })

    # Try a few times with backoff in case of transient blocks
    res = None
    for attempt in range(1, 4):
        try:
            res = session.get(SAPOL_URL, timeout=15)
            if res.status_code == 200:
                break
            else:
                print(f"⚠️ Fetch attempt {attempt} returned status {res.status_code}")
        except requests.RequestException as e:
            print(f"⚠️ Fetch attempt {attempt} failed: {e}")
        time.sleep(attempt * 1.5)

    # If we failed to fetch or got blocked (403), attempt a headless-browser fetch as a fallback.
    if not res or res.status_code == 403:
        print("🔁 Attempting headless-browser fetch fallback due to 403 or missing response...")
        html = fetch_with_playwright(SAPOL_URL)
        if html:
            class DummyResp:
                status_code = 200
                text = html
                headers = {}
            res = DummyResp()
        else:
            if not res:
                print("❌ Failed to fetch page (no response).")
            else:
                print(f"❌ Failed to fetch page, status code: {res.status_code}")
                print("Response headers:", dict(res.headers))
                snippet = res.text[:2000].replace('\n', ' ') if res.text else ''
                print("Page snippet:", snippet[:1000])
            return []

    # Parse the HTML and extract the relevant camera list
    soup = BeautifulSoup(res.text, "html.parser")

    # Try a few ways to locate camera entries because the site structure can change.
    # Prepare common date formats we may encounter in attributes or text
    iso_today = datetime.datetime.now(tz).strftime("%Y-%m-%d")
    long_today = datetime.datetime.now(tz).strftime("%d %B %Y")
    abbr_today = datetime.datetime.now(tz).strftime("%d %b %Y")
    date_variants = {today, iso_today, long_today, abbr_today}

    # 1) Directly search for elements that have data-value matching any date variant
    matched = []
    for dv in date_variants:
        matched.extend(soup.find_all(attrs={"data-value": dv}))

    # 2) If no data-value matches, look for list items that mention the date in their text
    if not matched:
        for li in soup.find_all("li"):
            text = li.get_text(" ", strip=True)
            if any(dv in text for dv in date_variants):
                matched.append(li)

    # 3) As a fallback, try to find any lists that look like camera lists (by class name hints)
    if not matched:
        possible_uls = []
        for cls in ("metrolist4", "metro-list", "camera-list", "showlist"):
            possible_uls.extend(soup.find_all("ul", class_=cls))
        for ul in possible_uls:
            for li in ul.find_all("li"):
                matched.append(li)

    # Extract camera location names from matched items
    raw_cameras = []
    for el in matched:
        # If the matched element is an li or contains an li, prefer the li text
        li = el if getattr(el, "name", None) == "li" else el.find_parent("li") or el
        cam_text = li.get_text(" ", strip=True)
        # Try to remove the date portion from the string if present (common formats)
        for dv in date_variants:
            cam_text = cam_text.replace(dv, "").strip()
        if cam_text:
            raw_cameras.append(cam_text)

    if not raw_cameras:
        print(f"❌ No metropolitan cameras found for {today}.")
        # For debugging, print a short snippet of the page where we expected the list
        snippet = res.text[:2000].replace('\n', ' ') if res.text else ''
        print("Page snippet:", snippet[:1000])
        return []

    # Geocode each camera location and calculate distance from user's location
    geolocator = Nominatim(user_agent="sapol_bot")
    camera_list = []

    for cam in raw_cameras:
        try:
            location = geolocator.geocode(f"{cam}, South Australia", timeout=10)
            if location:
                cam_coords = (location.latitude, location.longitude)
                distance_km = geodesic(user_location, cam_coords).km
                camera_list.append((cam, distance_km))
            else:
                camera_list.append((cam, None))
        except Exception as e:
            print(f"⚠️ Geocoding failed for {cam}: {e}")
            camera_list.append((cam, None))
        
        # Sleep to respect Nominatim’s rate limit
        time.sleep(1)

    # Sort cameras by distance (unknown distances go to the end)
    camera_list.sort(key=lambda x: x[1] if x[1] is not None else float("inf"))
    return camera_list

def send_to_discord(cameras):
    # Send the formatted camera list to a Discord webhook
    webhook = os.getenv("DISCORD_WEBHOOK")
    if not webhook:
        print("❌ Missing DISCORD_WEBHOOK environment variable.")
        return

    # Format the message with camera locations and distances
    if cameras:
        message = f"**Metropolitan speed cameras for {today}:**\n"
        for cam, dist in cameras:
            if dist is not None:
                message += f"• {cam} — `{dist:.1f} km`\n"
            else:
                message += f"• {cam} — `distance unknown`\n"
    else:
        message = f"No metropolitan cameras found for {today}."

    # Send message to Discord via POST request
    response = requests.post(webhook, json={"content": message})
    if response.status_code != 204:
        print(f"❌ Failed to send message to Discord. Status code: {response.status_code}")
    else:
        print("✅ Message sent successfully.")

# Main execution block: fetch today's cameras and send to Discord
if __name__ == "__main__":
    cameras = get_metropolitan_today()
    send_to_discord(cameras)
