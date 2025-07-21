# Import required libraries
import requests
from bs4 import BeautifulSoup
from geopy.distance import geodesic
from geopy.geocoders import Nominatim
import datetime
import pytz
import os
import time

# Set your location (example: Lockleys, SA)
user_location = (-34.9206, 138.5210)

# URL of SAPOL traffic camera listings
SAPOL_URL = "https://www.police.sa.gov.au/your-safety/road-safety/traffic-camera-locations"

# Set timezone to Adelaide and get today’s date in DD/MM/YYYY format
tz = pytz.timezone("Australia/Adelaide")
today = datetime.datetime.now(tz).strftime("%d/%m/%Y")

def get_metropolitan_today():
    # Fetch and parse SAPOL camera list for today's metropolitan locations
    print(f"📅 Fetching cameras for: {today}")
    res = requests.get(SAPOL_URL)
    
    # Check if the page loaded successfully
    if res.status_code != 200:
        print(f"❌ Failed to fetch page, status code: {res.status_code}")
        return []

    # Parse the HTML and extract the relevant camera list
    soup = BeautifulSoup(res.text, "html.parser")
    ul = soup.find("ul", class_="metrolist4")
    if not ul:
        print("❌ Could not find metropolitan camera list.")
        return []

    # Extract camera locations listed for today
    raw_cameras = [
        li.get_text(strip=True)
        for li in ul.find_all("li", class_="showlist")
        if li.get("data-value") == today
    ]

    if not raw_cameras:
        print("❌ No metropolitan cameras found for today.")
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
