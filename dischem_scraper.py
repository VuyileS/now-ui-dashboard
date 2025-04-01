import requests
from bs4 import BeautifulSoup
import json
import time
from urllib.parse import urljoin

headers = {
    "User-Agent": "Mozilla/5.0"
}

start_categories = [
    "https://www.dischem.co.za/health",
    "https://www.dischem.co.za/featured-brands/health",
    "https://www.dischem.co.za/medicine",
    "https://www.dischem.co.za/personal-care",
    "https://www.dischem.co.za/mother-and-baby",
    "https://www.dischem.co.za/vitamins-supplements",
    "https://www.dischem.co.za/featured-brands/household"
]

products = []
seen_product_keys = set()

def generate_product_key(name, price, url):
    return f"{name.strip()}|{price.strip()}|{url.strip()}"

def scrape_category(category_url):
    page = 1
    while True:
        url = f"{category_url}?p={page}"
        print(f"Scraping {url}...")
        res = requests.get(url, headers=headers)

        if res.status_code != 200:
            print("Error loading page or no more pages.")
            break

        soup = BeautifulSoup(res.text, "html.parser")
        product_cards = soup.select(".product-item")

        if not product_cards:
            print("No products found on this page.")
            break

        new_products_found = False

        for card in product_cards:
            name_tag = card.select_one(".product.name a")
            price_tag = card.select_one(".price")

            if name_tag and price_tag:
                name = name_tag.text.strip()
                url = urljoin("https://www.dischem.co.za", name_tag["href"])
                price = price_tag.text.strip()

                key = generate_product_key(name, price, url)

                if key not in seen_product_keys:
                    seen_product_keys.add(key)
                    new_products_found = True
                    products.append({
                        "name": name,
                        "url": url,
                        "price": price
                    })

        if not new_products_found:
            print("No new products found on this page. Ending.")
            break

        page += 1
        time.sleep(1)

for category in start_categories:
    scrape_category(category)

with open("dischem_products.json", "w") as f:
    json.dump(products, f, indent=2)

print(f"✅ Scraping complete. {len(products)} products saved to dischem_products.json")
