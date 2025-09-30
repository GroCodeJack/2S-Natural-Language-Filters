import requests
from bs4 import BeautifulSoup

def scrape_2ndswing(url: str):
    """Scrape product data from 2nd Swing website."""
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        soup = BeautifulSoup(requests.get(url, headers=headers, timeout=10).text, "html.parser")
        all_data = []
        total_count = None
        applied_filters = []
        next_page_url = None
        no_results = False
        
        # Check for no results message first
        no_results_element = soup.select_one('div.message.info.empty')
        if no_results_element and "We can't find products matching the selection" in no_results_element.get_text():
            no_results = True
        
        # Capture total count
        count_tag = soup.select_one('p.toolbar-amount span.toolbar-number:last-child')
        if count_tag:
            try:
                total_count = int(count_tag.get_text(strip=True).replace(',', ''))
            except ValueError:
                total_count = None

        # Capture applied filters (label/value pairs), if present
        # This targets structures like:
        # <ol class="items">
        #   <li class="item"> <span class="filter-label">Brand</span> <span class="filter-value">Ping</span> ...
        # We scope broadly to avoid missing due to container class name differences.
        for li in soup.select('ol.items li.item'):
            label_el = li.select_one('.filter-label')
            value_el = li.select_one('.filter-value')
            if label_el and value_el:
                label = label_el.get_text(strip=True)
                value = value_el.get_text(strip=True)
                if label and value:
                    applied_filters.append({
                        "label": label,
                        "value": value,
                    })

        # Capture next page URL from pagination
        # Look for the "next" button or page 2 if on page 1
        next_link = soup.select_one('ul.pages-items li.pages-item-next a.next')
        if not next_link:
            # Fallback: look for page 2 link if we're on page 1
            next_link = soup.select_one('ul.pages-items li.item a[href*="p=2"]')
        
        if next_link and next_link.get('href'):
            href = next_link['href']
            # Fix HTML entity encoding issues
            import html
            href = html.unescape(href)
            
            # Ensure we have a full URL
            if href.startswith('/'):
                next_page_url = 'https://www.2ndswing.com' + href
            elif href.startswith('http'):
                next_page_url = href
            else:
                next_page_url = None
            print(f"Next page URL found: {next_page_url}")
        else:
            print("No next page URL found")

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
            new_price = new_url = used_price = used_url = None
            
            if not parent_model:
                price_div = card.find("div", class_="current-price")
                price = price_div.get_text(strip=True) if price_div else "N/A"
                cond_div = card.find("div", class_="pmp-product-condition")
                condition = cond_div.get_text(strip=True) if cond_div else "N/A"
            else:
                # Extract New and Used pricing for parent models
                new_used_links = card.find_all("a", class_="new-used-listing-link")
                for link in new_used_links:
                    href = link.get("href", "")
                    price_span = link.find("span", class_="price")
                    
                    if "new_used_filter=New" in href and price_span:
                        new_price = price_span.get_text(strip=True)
                        new_url = href
                    elif "new_used_filter=Used" in href and price_span:
                        used_price = price_span.get_text(strip=True)
                        used_url = href

            all_data.append({
                "brand": brand,
                "model": model,
                "img_url": img_url,
                "url": product_url,
                "price": price,
                "condition": condition,
                "parent_model": parent_model,
                "new_price": new_price,
                "new_url": new_url,
                "used_price": used_price,
                "used_url": used_url,
                "attrs": attrs,
            })
        return all_data, total_count, applied_filters, next_page_url, no_results
    except Exception as e:
        print("Scrape error:", e)
        return [], None, [], None, False
 