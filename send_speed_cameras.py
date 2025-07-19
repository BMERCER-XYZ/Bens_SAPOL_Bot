import requests
from bs4 import BeautifulSoup
from datetime import datetime

def fetch_speed_cameras():
    url = "https://www.police.sa.gov.au/your-safety/road-safety/traffic-camera-locations"  # Use the actual URL

    # Fetch page content
    response = requests.get(url)
    if response.status_code != 200:
        print(f"Failed to fetch page, status code {response.status_code}")
        return

    soup = BeautifulSoup(response.text, "html.parser")

    # Format date to match site header exactly
    today = datetime.now().strftime("%A, %B %d, %Y")
    print(f"Looking for header: {today}")

    # Find all headers with the accordion class
    headers = soup.find_all("div", class_="accordion accordion-open")

    # Find the header matching today's date
    header = None
    for h in headers:
        if h.text.strip() == today:
            header = h
            break

    if header is None:
        print(f"No header found for {today}")
        return

    # Assuming the camera info is in the next sibling div or element after header
    camera_info = header.find_next_sibling()
    if camera_info is None:
        print("No camera info found after header.")
        return

    # Print the text content for debugging
    print("Speed camera info for today:")
    print(camera_info.get_text(separator="\n").strip())

if __name__ == "__main__":
    fetch_speed_cameras()
