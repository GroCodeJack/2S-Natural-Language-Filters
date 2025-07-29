import requests
from bs4 import BeautifulSoup

def scrape_2ndswing(url: str):
    """Scrape product data from 2nd Swing website."""
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        soup = BeautifulSoup(requests.get(url, headers=headers, timeout=10).text, "html.parser")
        all_data = []
        total_count = None
        
        # Capture total count
        count_tag = soup.select_one('p.toolbar-amount span.toolbar-number:last-child')
        if count_tag:
            try:
                total_count = int(count_tag.get_text(strip=True).replace(',', ''))
            except ValueError:
                total_count = None

        for card in soup.select("div.product-box.product-item-info"):
            brand = card.find("div", class_="product-brand")
            brand = brand.get_text(strip=True) if brand else "N/A"
            
            model_tag = card.find("div", class_="pmp-product-category") or card.find("div", class_="p-title")
            model = model_tag.get_text(strip=True) if model_tag else "N/A"
            
            img_tag = card.find("img", class_="product-image-photo")
            img_url = img_tag["src"] if img_tag else ""
            
            link_tag = card.select_one("a.product.photo.product-item-photo")
            product_url = link_tag["href"] if link_tag else ""

            parent_model = card.get("data-itemhasused") == "1" and card.get("data-hasnewvariants") == "1"

            # Capture ALL attrs dynamically
            attrs = {}
            attr_block = card.find("div", class_="pmp-attribute")
            if attr_block:
                for lbl in attr_block.select("span.pmp-attribute-label"):
                    key = lbl.get_text(strip=True).rstrip(":").lower()
                    val = lbl.next_sibling
                    while val and getattr(val, "name", None) == "br":
                        val = val.next_sibling
                    if val:
                        attrs[key] = val.strip() if isinstance(val, str) else val.get_text(strip=True)

            # Price & condition (if single‑used)
            price = condition = "N/A"
            if not parent_model:
                price_div = card.find("div", class_="current-price")
                price = price_div.get_text(strip=True) if price_div else "N/A"
                cond_div = card.find("div", class_="pmp-product-condition")
                condition = cond_div.get_text(strip=True) if cond_div else "N/A"

            all_data.append({
                "brand": brand,
                "model": model,
                "img_url": img_url,
                "url": product_url,
                "price": price,
                "condition": condition,
                "parent_model": parent_model,
                "attrs": attrs,
            })
        return all_data, total_count
    except Exception as e:
        print("Scrape error:", e)
        return [], None 