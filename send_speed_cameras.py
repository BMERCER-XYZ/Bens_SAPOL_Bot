# Import required libraries
import requests
import math
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

# Set timezone to Adelaide and get today’s date in DD/MM/YYYY format
tz = pytz.timezone("Australia/Adelaide")
today = datetime.datetime.now(tz).strftime("%d/%m/%Y")

# Adelaide CBD Coordinates for region calculation
ADELAIDE_CBD_COORDS = (-34.9285, 138.6007)


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

def generate_map_image(cameras: List[Dict[str, Any]]) -> Optional[str]:
    """Generates a static map image of camera locations using Folium and Playwright."""
    if not cameras:
        return None

    print("🗺️ Generating map preview...")
    try:
        # Initialize map (bounds will be set later)
        m = folium.Map(tiles="CartoDB positron")

        bounds_points = []

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
            
            if cam.get('lat') is not None:
                bounds_points.append([cam['lat'], cam['lon']])
        
        if not bounds_points:
            return None

        # Fit bounds to show all cameras
        if len(bounds_points) == 1:
            # If only one point, center and zoom
            m.location = bounds_points[0]
            m.zoom_start = 14
        else:
            m.fit_bounds(bounds_points, padding=(30, 30))
        
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
    # Fetch and parse SAPOL camera list for today's metropolitan locations
    print(f"📅 Fetching cameras for: {today}")

    # Fetch directly using Playwright
    html = fetch_with_playwright(SAPOL_URL)
    if not html:
        print("❌ Failed to fetch page using Playwright.")
        return []

    # Parse the HTML and extract the relevant camera list
    soup = BeautifulSoup(html, "html.parser")

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
        # For debugging, print a short snippet of the HTML
        snippet = html[:2000].replace('\n', ' ') if html else ''
        print("Page snippet:", snippet[:1000])
        return []

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
    return camera_list

def send_to_discord(cameras, image_path: Optional[str] = None):
    # Send the formatted camera list to a Discord webhook
    webhook = os.getenv("DISCORD_WEBHOOK")
    if not webhook:
        print("❌ Missing DISCORD_WEBHOOK environment variable.")
        return

    if not cameras:
        message = f"No metropolitan cameras found for {today}."
        requests.post(webhook, json={"content": message})
        return

    # Group cameras by region
    regions = {
        "CBD": [],
        "Northern Suburbs": [],
        "Eastern Suburbs": [],
        "Southern Suburbs": [],
        "Western Suburbs": [],
        "Unknown": []
    }
    
    for cam in cameras:
        reg = cam.get("region", "Unknown")
        if reg in regions:
            regions[reg].append(cam)
        else:
            regions["Unknown"].append(cam)

    # Build the message
    message = f"**Metropolitan speed cameras for {today}:**\n"
    
    # Order of display
    display_order = ["Northern Suburbs", "Eastern Suburbs", "Southern Suburbs", "Western Suburbs", "CBD", "Unknown"]
    
    for region_name in display_order:
        region_cams = regions[region_name]
        if region_cams:
            message += f"\n**{region_name}**\n"
            for cam in region_cams:
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
    cameras = get_metropolitan_today()
    
    # Generate map if we have cameras
    map_image = None
    if cameras:
        map_image = generate_map_image(cameras)
        
    send_to_discord(cameras, map_image)
    
    # Clean up
    if map_image and os.path.exists(map_image):
        try:
            os.remove(map_image)
        except Exception:
            pass

# Main execution block: fetch today's cameras and send to Discord
if __name__ == "__main__":
    cameras = get_metropolitan_today()
    send_to_discord(cameras)
