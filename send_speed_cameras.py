import requests
from bs4 import BeautifulSoup
import datetime
import os

SAPOL_URL = "https://www.police.sa.gov.au/your-safety/road-safety/traffic-camera-locations"

# Today's date in DD/MM/YYYY format matching data-value attribute
today = datetime.datetime.now().strftime("%d/%m/%Y")  # e.g. "19/07/2025"

def get_metropolitan_today():
    res = requests.get(SAPOL_URL)
    if res.status_code != 200:
        print(f"Failed to fetch page, status code: {res.status_code}")
        return []

    soup = BeautifulSoup(res.text, "html.parser")

    # Find the <ul> with class "metrolist4" (Metropolitan cameras)
    ul = soup.find("ul", class_="metrolist4")
    if not ul:
        print("Could not find metropolitan camera list.")
        return []

    # Filter <li> with data-value == today's date
    cameras = [
        li.get_text(strip=True)
        for li in ul.find_all("li", class_="showlist")
        if li.get("data-value") == today
    ]

    return cameras

def send_to_discord(cameras):
    webhook = os.getenv("DISCORD_WEBHOOK")
    if not webhook:
        print("Missing DISCORD_WEBHOOK environment variable.")
        return

    if cameras:
        message = f"**Metropolitan speed cameras for {today}:**\n" + "\n".join(f"• {cam}" for cam in cameras)
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
