import requests
from bs4 import BeautifulSoup
import datetime
import os
from geopy.distance import geodesic

SAPOL_URL = "https://www.police.sa.gov.au/your-safety/road-safety/traffic-camera-locations"
YOUR_LOCATION = (-34.9247, 138.5371)  # Lockleys, SA (replace with your actual coords)

today = datetime.datetime.now().strftime("%d/%m/%Y")

# A simple address-to-coordinates cache
geocode_cache = {}

def geocode_address(address):
    if address in geocode_cache:
        return geocode_cache[address]
    try:
        res = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": f"{address}, South Australia", "format": "json", "limit": 1},
            headers={"User-Agent": "SAPOL-Bot/1.0"},
        )
        data = res.json()
        if data:
            lat = float(data[0]["lat"])
            lon = float(data[0]["lon"])
            geocode_cache[address] = (lat, lon)
            return (lat, lon)
    except Exception as e:
        print(f"Failed to geocode '{address}': {e}")
    return None

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

    raw_cameras = [
        li.get_text(strip=True)
        for li in ul.find_all("li", class_="showlist")
        if li.get("data-value") == today
    ]

    # Sort cameras by distance from YOUR_LOCATION
    camera_with_distances = []
    for cam in raw_cameras:
        location = geocode_address(cam)
        if location:
            dist = geodesic(YOUR_LOCATION, location).km
            camera_with_distances.append((cam, dist))
        else:
            camera_with_distances.append((cam, float('inf')))  # If geocoding fails, put at end

    # Sort by distance (closest first)
    camera_with_distances.sort(key=lambda x: x[1])

    return [cam for cam, _ in camera_with_distances]

def send_to_discord(cameras):
    webhook = os.getenv("DISCORD_WEBHOOK")
    if not webhook:
        print("Missing DISCORD_WEBHOOK environment variable.")
        return

    if cameras:
        message = f"**Metropolitan speed cameras for {today} (sorted by proximity):**\n" + \
                  "\n".join(f"• {cam}" for cam in cameras)
    else:
        message = f"No metropolitan cameras found for {today}."

    response = requests.post(webhook, json={"content": message})
    if response.status_code != 204:
        print(f"Failed to send message to Discord. Status code: {response.status_code}")
    else:
        print("Message sent successfully.")

if __name__ == "__main__":
    cameras = get_metropolitan_today()
    send_to_discord(cameras)
