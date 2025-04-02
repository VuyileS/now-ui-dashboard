from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
import json
import time
import requests

# Step 1: Get condition URLs
def get_condition_urls():
    response = requests.get("https://www.dischem.co.za/health-conditions-a-z")
    soup = BeautifulSoup(response.text, "html.parser")
    links = soup.select("a")
    condition_urls = list({
        link['href'] if link['href'].startswith("http") else "https://www.dischem.co.za" + link['href']
        for link in links if link.get("href") and "/articles/post/" in link['href']
    })
    return condition_urls

# Step 2: Scrape each condition page
def scrape_condition(driver, url):
    data = {"url": url}
    try:
        driver.get(url)
        time.sleep(3)  # Wait for page to load

        soup = BeautifulSoup(driver.page_source, "html.parser")
        title_tag = soup.select_one("h1.page-title")
        data["title"] = title_tag.text.strip() if title_tag else ""

        # ✅ The actual content is inside this div
        content_div = soup.find("div", class_="article-content")

        if content_div:
            current_heading = None
            for tag in content_div.find_all(["h2", "h3", "p"]):
                if tag.name in ["h2", "h3"]:
                    current_heading = tag.get_text(strip=True)
                    data[current_heading] = ""
                elif tag.name == "p" and current_heading:
                    data[current_heading] += tag.get_text(strip=True) + "\n"

        return data if len(data.keys()) > 2 else None

    except Exception as e:
        print(f"❌ Failed to scrape {url}: {e}")
        return None


# Step 3: Main function
def scrape_all_conditions():
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)

    urls = get_condition_urls()
    print(f"🔗 Found {len(urls)} condition links")
    all_data = []

    for idx, url in enumerate(urls):
        print(f"🔍 Scraping [{idx + 1}/{len(urls)}]: {url}")
        result = scrape_condition(driver, url)
        if result:
            all_data.append(result)
        time.sleep(1.2)

    driver.quit()

    with open("dischem_conditions.json", "w", encoding="utf-8") as f:
        json.dump(all_data, f, indent=2, ensure_ascii=False)

    print(f"\n✅ Done. Scraped {len(all_data)} conditions.")

if __name__ == "__main__":
    scrape_all_conditions()
