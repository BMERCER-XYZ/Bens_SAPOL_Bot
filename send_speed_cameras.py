import requests
from bs4 import BeautifulSoup
import datetime
import os
from geopy.distance import geodesic
from geopy.geocoders import Nominatim
import re

# Your fixed location (Lockleys SA as example)
HOME_SUBURB = "Lockleys, South Australia"
FAVORITE_SUBURBS = {"lockleys", "brooklyn park", "findon", "henley beach", "mile end", "fulham", "fulham gardens", "west beach", "seaton", "grange", "torrensville", "underdale", "woodville", "woodville south", "woodville west", "adelaide"}

SAPOL_URL = "https://www.police.sa.gov.au/your-safety/road-safety/traffic-camera-locations"
today = datetime.datetime.now().strftime("%d/%m/%Y")

geolocator = Nominatim(user_agent="sapol_bot")
home_coords = geolocator.geocode(HOME_SUBURB)
if not home_coords:
    raise ValueError(f"Could not locate your home suburb: {HOME_SUBURB}")

def get_metropolitan_today():
    res = requests.get(SAPOL_URL)
    if res.status_code != 200:
        print(f"Failed to fetch page, status code: {res.status_code}")
        return []

    soup = BeautifulSoup(res.text, "html.parser")
    ul = soup.find("ul", class_="metrolist4")
    if not ul:
        print("Could not find metropolitan camera list.")
        return []

    cameras = []
    for li in ul.find_all("li", class_="showlist"):
        if li.get("data-value") == today:
            cameras.append(li.get_text(strip=True))

    return cameras

def extract_suburb(camera_text):
    match = re.search(r"\b([A-Z][a-z]+(?: [A-Z][a-z]+)?)\b", camera_text)
    return match.group(1) if match else None

def sort_and_annotate_cameras(cameras):
    sorted_list = []
    for cam in cameras:
        suburb = extract_suburb(cam)
        if not suburb:
            continue
        try:
            loc = geolocator.geocode(f"{suburb}, South Australia")
            if not loc:
                continue
            cam_coords = (loc.latitude, loc.longitude)
            dist_km = geodesic((home_coords.latitude, home_coords.longitude), cam_coords).km
            is_fav = suburb.lower() in FAVORITE_SUBURBS
            sorted_list.append((cam, dist_km, is_fav))
        except Exception as e:
            print(f"Error geocoding suburb '{suburb}': {e}")
            continue

    return sorted(sorted_list, key=lambda x: x[1])

def send_to_discord(sorted_cameras):
    webhook = os.getenv("DISCORD_WEBHOOK")
    if not webhook:
        print("Missing DISCORD_WEBHOOK environment variable.")
        return

    if not sorted_cameras:
        message = f"No metropolitan cameras found for {today}."
    else:
        lines = []
        for cam, dist_km, is_fav in sorted_cameras:
            highlight = ">" if is_fav else ""
            lines.append(f"{highlight}• {cam} — {dist_km:.1f} km")

        message = f"**Metropolitan speed cameras for {today}:**\n" + "\n".join(lines)

    response = requests.post(webhook, json={"content": message})
    if response.status_code != 204:
        print(f"Failed to send message to Discord. Status code: {response.status_code}")
    else:
        print("Message sent successfully.")

if __name__ == "__main__":
    cameras = get_metropolitan_today()
    sorted_cameras = sort_and_annotate_cameras(cameras)
    send_to_discord(sorted_cameras)
