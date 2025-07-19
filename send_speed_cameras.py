import os
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
import json
import time

# --- Configuration ---
USER_LOCATION = (-34.918, 138.526)  # Lockleys, SA (change to your location)
CACHE_FILE = "geocode_cache.json"
WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK")
URL = "https://www.police.sa.gov.au/your-safety/road-safety/traffic-camera-locations"

print(f"Using webhook: {WEBHOOK_URL}")

# --- Load or initialize geocoding cache ---
if os.path.exists(CACHE_FILE):
    with open(CACHE_FILE, "r") as f:
        geocode_cache = json.load(f)
else:
    geocode_cache = {}

# --- Setup geopy geocoder ---
geolocator = Nominatim(user_agent="sapol_cam_locator")

def get_distance(address):
    if address in geocode_cache:
        coords = geocode_cache[address]
    else:
        try:
            location = geolocator.geocode(address + ", South Australia", timeout=10)
            if location:
                coords = (location.latitude, location.longitude)
                geocode_cache[address] = coords
                with open(CACHE_FILE, "w") as f:
                    json.dump(geocode_cache, f, indent=2)
                time.sleep(1)  # Be polite to the server
            else:
                return float("inf")
        except:
            return float("inf")
    return geodesic(USER_LOCATION, coords).km

# --- Fetch and parse camera list ---
response = requests.get(URL)
soup = BeautifulSoup(response.content, "html.parser")

today = datetime.now().strftime("%A, %d %B %Y")
header = soup.find("h4", string=today)

if not header:
    print(f"No header found for {today}")
    exit()

ul = header.find_next("ul", class_="metrolist4")
if not ul:
    print("Could not find metropolitan camera list.")
    exit()

metro_locations = [li.get_text(strip=True) for li in ul.find_all("li") if li.get("data-value") == datetime.now().strftime("%d/%m/%Y")]

if not metro_locations:
    print(f"No metropolitan cameras found for {today}.")
    exit()

# --- Sort by distance ---
sorted_locations = sorted(metro_locations, key=get_distance)

# --- Format message ---
message = f"**SA Police Speed Cameras for {today}**\n"
for loc in sorted_locations:
    message += f"- {loc}\n"

print(message)

# --- Send to Discord ---
if WEBHOOK_URL:
    requests.post(WEBHOOK_URL, json={"content": message})
else:
    print("DISCORD_WEBHOOK environment variable not set.")
