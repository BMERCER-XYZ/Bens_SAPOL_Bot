import requests
from bs4 import BeautifulSoup
from geopy.distance import geodesic
from geopy.geocoders import Nominatim
import datetime
import os
import time

# Set your location (example: Lockleys, SA)
user_location = (-34.9206, 138.5210)

SAPOL_URL = "https://www.police.sa.gov.au/your-safety/road-safety/traffic-camera-locations"
today = datetime.datetime.now().strftime("%d/%m/%Y")  # e.g. "19/07/2025"

def get_metropolitan_today():
    print(f"📅 Fetching cameras for: {today}")
    res = requests.get(SAPOL_URL)
    if res.status_code != 200:
        print(f"❌ Failed to fetch page, status code: {res.status_code}")
        return []

    soup = BeautifulSoup(res.text, "html.parser")
    ul = soup.find("ul", class_="metrolist4")
    if not ul:
        print("❌ Could not find metropolitan camera list.")
        return []

    raw_cameras = [
        li.get_text(strip=True)
        for li in ul.find_all("li", class_="showlist")
        if li.get("data-value") == today
    ]

    if not raw_cameras:
        print("❌ No metropolitan cameras found for today.")
        return []

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
        time.sleep(1)  # Respect Nominatim rate limit

    # Sort by distance (Unknowns last)
    camera_list.sort(key=lambda x: x[1] if x[1] is not None else float("inf"))
    return camera_list

def send_to_discord(cameras):
    webhook = os.getenv("DISCORD_WEBHOOK")
    if not webhook:
        print("❌ Missing DISCORD_WEBHOOK environment variable.")
        return

    if cameras:
        message = f"**Metropolitan speed cameras for {today}:**\n"
        for cam, dist in cameras:
            if dist is not None:
                message += f"• {cam} — `{dist:.1f} km`\n"
            else:
                message += f"• {cam} — `distance unknown`\n"
    else:
        message = f"No metropolitan cameras found for {today}."

    response = requests.post(webhook, json={"content": message})
    if response.status_code != 204:
        print(f"❌ Failed to send message to Discord. Status code: {response.status_code}")
    else:
        print("✅ Message sent successfully.")

if __name__ == "__main__":
    cameras = get_metropolitan_today()
    send_to_discord(cameras)