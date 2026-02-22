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

# List of greetings for Maddy
GREETINGS = [
    "Good morning Maddy! 🌞 Here are the speed camera locations for {today}:",
    "Rise and shine Maddy! ☕ Check out the traffic cameras for {today}:",
    "Hello Maddy! 🚗 Stay safe on the roads! Here are the cameras for {today}:",
    "Top of the morning to you Maddy! 🍀 Speed camera list for {today}:",
    "Happy day Maddy! Watch out for these cameras today ({today}):",
    "Wakey wakey Maddy! Here is your daily traffic camera update for {today}:",
    "Greetings Maddy! 🚦 Here is where the cameras are hiding today ({today}):",
    "Good day Maddy! Hope you have a wonderful day. Here are today's camera locations for {today}:",
    "Morning Maddy! Just a heads up, here's the rundown of speed cameras for {today}:",
    "Hey Maddy! Your daily camera intel for {today} has arrived:",
    "Howdy Maddy! The speed camera spots for {today} are as follows:",
    "Morning, Maddy! Don't get caught out - here are the cameras for {today}:",
    "A fresh day, a fresh list, Maddy! Speed cameras for {today}:",
    "Bonjour Maddy! Here are the camera locations for {today}, plan your route accordingly:",
    "Maddy, your daily alert! The camera locations for {today} are here:",
    "Yo Maddy! 🤘 Here's the lowdown on speed cameras for {today}:",
    "What's up, Maddy? Your daily dose of camera locations for {today} is in!",
    "Another day, another camera update for Maddy! {today}'s locations:",
    "Heads up Maddy! Navigate safely with {today}'s camera list:",
    "Morning sunshine Maddy! ☀️ Your speed camera guide for {today}:",
    "G'day Maddy! Here's the latest on the traffic cameras for {today}:",
    "For your eyes only, Maddy! Speed camera locations for {today}:",
    "Stay sharp, Maddy! Here's where to find the cameras on {today}:",
    "Top of the mornin', Maddy! Time for your speed camera brief for {today}:",
    "Sending good vibes, Maddy! And today's speed camera locations for {today}:",
    "Good to see you, Maddy! Here are the camera details for {today}:",
    "Maddy, reporting in! Speed cameras for {today} are at these spots:",
    "Catch you later, Maddy! But first, the camera locations for {today}:",
    "Start your engines, Maddy! And check out the speed cameras for {today}:",
    "Beep beep, Maddy! Here are the cameras for {today}:",
    "Rise and shine, superstar Maddy! 🌟 Your camera intel for {today} is hot off the press:",
    "Good morning, fabulous Maddy! Here's your essential speed camera update for {today}:",
    "Hey there, Maddy! Just dropping by with the camera locations for {today}. Drive safe!",
    "Your daily dose of speed camera awareness, Maddy! Locations for {today}:",
    "Sending some Maddy-magic your way with today's camera spots ({today}):",
    "Happy driving, Maddy! Here are the speed camera details for {today}:",
    "To the amazing Maddy: Your camera report for {today} is ready!",
    "Maddy, Maddy, quite contrary, how do your speed cameras grow? Find out for {today}:",
    "Another beautiful day, Maddy! Here's what you need to know about cameras for {today}:",
    "Morning, champion Maddy! 🏆 Get ready for {today} with these camera locations:",
    "Alert, Maddy! Your speed camera briefing for {today} awaits:",
    "Wishing you a safe commute, Maddy! Here are the cameras for {today}:",
    "Your daily heads-up, Maddy! Speed camera placements for {today}:",
    "Maddy, let's make it a safe one! Here are the camera locations for {today}:",
    "Keep an eye out, Maddy! Here's your speed camera list for {today}:",
    "Good vibrations and camera locations, Maddy! All for {today}:",
    "May your day be camera-free, Maddy! (Unless you check this list for {today}):",
    "Maddy, your mission, should you choose to accept it: Avoid these cameras on {today}:",
    "Buenos días, Maddy! Here are the speed camera locations to navigate around for {today}:",
    "Maddy, adventurer of the roads! Here's your guide to today's cameras ({today}):",
    "Have a fantastic day, Maddy! But first, a quick look at the cameras for {today}:",
    "The early bird catches the... camera locations, Maddy! For {today}:",
    "Your loyal bot reports for duty, Maddy! Here are the cameras for {today}:",
    "Power up, Maddy! Your morning camera update for {today} has arrived:",
    "Don't say I didn't warn you, Maddy! Here are the cameras for {today}:",
    "Driving with Maddy in mind! Speed camera locations for {today}:",
    "Here's the scoop, Maddy! All about the cameras for {today}:",
    "For the discerning driver, Maddy: The speed camera locations for {today}:",
    "Good morning, speed demon Maddy! Just kidding! Here are the cameras for {today}:",
    "Maddy, your watchful eye is needed! Check these camera spots for {today}:",
    "A little birdy told me you need camera locations, Maddy! For {today}:",
    "To the best Maddy, here are the speed camera updates for {today}:",
    "Your daily dose of road wisdom, Maddy! Cameras for {today}:",
    "Stay golden, Maddy, and check out these camera locations for {today}:",
    "Maddy, the roads are calling! Here are the cameras for {today}:",
    "Another day, another chance to avoid fines, Maddy! Cameras for {today}:",
    "Sending positive vibes and camera data your way, Maddy! For {today}:",
    "May your journey be swift and safe, Maddy! Here are today's cameras ({today}):",
    "Hey Maddy, good morning! Here are the latest camera locations for {today}:",
    "Rise and shine, Maddy! Your daily camera briefing for {today} is ready:",
    "What's cookin', Maddy? Just your speed camera locations for {today}:",
    "Hope your coffee's strong, Maddy! Here's your camera update for {today}:",
    "Stay alert, Maddy! Here are the cameras watching out for {today}:",
    "Good morning, road warrior Maddy! Your camera intel for {today} is here:",
    "For a smooth drive, Maddy, check these cameras for {today}:",
    "Maddy, your commute just got smarter with these camera locations for {today}:",
    "Another glorious morning, Maddy! And your speed camera list for {today}:",
    "To the coolest Maddy, here are the speed camera locations for {today}:",
    "Good morning, Maddy! Get your engines ready, but watch out for these cameras on {today}:",
    "Maddy, your personal traffic camera concierge is here! Locations for {today}:",
    "Wishing you an alert day, Maddy! Here are the camera hot spots for {today}:",
    "The roads are open, Maddy! And these are the cameras to know about for {today}:",
    "Keep your eyes peeled, Maddy! Today's speed camera locations for {today}:",
    "Have a great morning, Maddy! Here's the camera info for {today}:",
    "Hey Maddy, time for your daily dose of speed camera enlightenment for {today}:",
    "Maddy, your road trip planning starts here! Cameras for {today}:",
    "Let's beat those cameras, Maddy! Here's the list for {today}:",
    "Good morning, Maddy! Here's the lowdown on where the speed cameras are at {today}:",
    "Maddy, your chariot awaits! Check these cameras for {today} first:",
    "Knock knock, Maddy! Who's there? Speed cameras for {today}!",
    "Greetings, Earthling Maddy! Here is your terrestrial camera data for {today}:",
    "Ahoi Maddy! Navigate the seas of asphalt safely with today's camera list ({today}):",
    "Maddy! Stop! Collaborate and listen! Here are the cameras for {today}:",
    "Just for you, Maddy: The secret map of speed cameras for {today}:",
    "Don't rush, Maddy! Or at least know where these cameras are on {today}:",
    "Maddy, keep it breezy and easy. Avoid these cameras on {today}:",
    "Salutations Maddy! Your daily dispatch of traffic cam locations for {today}:",
    "Hola Maddy! Watch your speed at these spots on {today}:",
    "Maddy, maximize your day and minimize your fines! Cameras for {today}:",
    "Focus, Maddy! Here are the critical camera coordinates for {today}:",
    "Ready, Set, Go Maddy! But watch out for cameras here on {today}:",
    "Zoom zoom Maddy! But not too fast past these cameras on {today}:",
    "Maddy's Morning Memo: Speed camera locations for {today}:",
    "Maddy, wake up! Cameras for {today}:",
    "Psst Maddy... here are the secrets for {today}:",
    "Incoming transmission for Agent Maddy: Camera locations for {today}.",
    "Ding dong! Maddy's daily camera delivery for {today} is here.",
    "Don't let the cameras bite, Maddy! Locations for {today}:",
    "Maddy + Coffee + Camera List for {today} = A good morning.",
    "Buckle up Maddy! Here is the intel for {today}:",
    "On your marks, get set, go Maddy! (But watch out for cameras on {today}):",
    "Maddy, check your mirrors and this list for {today}:",
    "Safe travels Maddy! Here is the camera map for {today}:",
    "Smile Maddy! But maybe not at these cameras on {today}:",
    "Maddy's road survival guide for {today}:",
    "Good morning! Maddy's personal camera radar for {today}:",
    "Carpe Diem, Maddy! And Carpe Camera List for {today}:",
    "Maddy, knowledge is power. Here is your power for {today}:",
    "Greetings from the digital ether, Maddy. Cameras for {today}:",
    "Just another manic morning, Maddy? Here are the cameras for {today}:",
    "Cruising down the street... carefully, Maddy! Cameras for {today}:",
    "Maddy, let's keep that driving record clean. Cameras for {today}:",
    "Hello from the bot cave, Maddy! Camera locations for {today}:",
    "Maddy, start your engines! But check this list for {today} first:",
    "Fuel up, Maddy! Here is your traffic intel for {today}:",
    "Navigate like a pro, Maddy! Avoid these cameras on {today}:",
    "Smooth sailing ahead, Maddy (if you watch out for these cameras on {today}):",
    "Maddy, you're going places! Just don't get flashed at these spots on {today}:",
    "The road to success is paved with... speed cameras? Not for you, Maddy! Locations for {today}:",
    "Maddy, stay fast (but legal)! Cameras for {today}:",
    "Your daily navigation hack, Maddy! Camera list for {today}:",
    "Forewarned is forearmed, Maddy! Speed cameras for {today}:",
    "Hey Maddy, keep that cash in your pocket and avoid these fines on {today}:",
    "Silence is golden, but this camera list for {today} is priceless, Maddy:",
    "Maddy, don't let a flash ruin your dash! Cameras for {today}:",
    "A wise Maddy once checked the camera list for {today}...",
    "Driving safe is driving smart, Maddy. Locations for {today}:",
    "Maddy, master of the road! Here are the obstacles for {today}:",
    "Clear eyes, full hearts, can't lose (unless you speed here on {today}, Maddy):",
    "Maddy's daily decree: Watch out for cameras on {today}:",
    "Speed limits are just suggestions? No, they are laws, Maddy! Cameras for {today}:",
    "Maddy, fly like the wind! (But slow down here on {today}):",
    "Attention Maddy: Speed enforcement active at these locations on {today}:",
    "The open road calls, Maddy! Answer it, but check these cameras for {today}:",
    "Maddy, your commute defense system activated for {today}. Locations:",
    "Be the best driver you can be, Maddy! Watch these spots on {today}:",
    "Legendary driver Maddy coming through! Dodging cameras on {today}:",
    "Maddy, let's make today ticket-free! Cameras for {today}:"
]


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
    greeting = random.choice(GREETINGS).format(today=date_for_message)
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
