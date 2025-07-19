import os
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK")
URL = "https://www.police.sa.gov.au/online-services/speed-camera-locations"

# Get today's date in correct format (e.g. 19/07/2025)
today = datetime.now().strftime("%d/%m/%Y")

print(f"Using webhook: {WEBHOOK_URL}")
print(f"Fetching data for: {today}")

# Fetch and parse
response = requests.get(URL)
soup = BeautifulSoup(response.text, "html.parser")

# Find all <li> tags in the metrolist4 <ul> with the correct date
camera_list = soup.select(f'ul.metrolist4 li.showlist[data-value="{today}"]')

if not camera_list:
    print(f"No cameras found for {today}")
    exit()

# Prepare message
locations = [li.text.strip() for li in camera_list]
message = "**SAPOL Metropolitan Speed Cameras for Today:**\n" + "\n".join(f"- {loc}" for loc in locations)

# Send to Discord
response = requests.post(WEBHOOK_URL, json={"content": message})

if response.status_code == 204:
    print("✅ Successfully sent message to Discord.")
else:
    print(f"❌ Failed to send message. Status: {response.status_code} Response: {response.text}")
