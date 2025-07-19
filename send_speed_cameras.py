import os
import requests
from bs4 import BeautifulSoup
from datetime import datetime

WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK")
URL = "https://www.police.sa.gov.au/online-services/speed-camera-locations"

today = datetime.now().strftime("%d/%m/%Y")
print(f"Fetching cameras for: {today}")

response = requests.get(URL)
soup = BeautifulSoup(response.text, "html.parser")

camera_list = soup.select(f'ul.metrolist4 li.showlist[data-value="{today}"]')

if not camera_list:
    print(f"No metropolitan cameras found for {today}")
    exit()

locations = [li.text.strip() for li in camera_list]
message = "**SAPOL Metropolitan Speed Cameras for Today:**\n" + "\n".join(f"- {loc}" for loc in locations)

res = requests.post(WEBHOOK_URL, json={"content": message})
if res.status_code == 204:
    print("✅ Message sent to Discord.")
else:
    print(f"❌ Failed to send. Status: {res.status_code} Response: {res.text}")
