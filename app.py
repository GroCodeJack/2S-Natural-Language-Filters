import os
from flask import Flask, request, redirect, url_for, render_template_string
from openai import OpenAI
import requests
from bs4 import BeautifulSoup

app = Flask(__name__)

# We'll store results in these globals to keep it easy.
last_products = []
last_query = ""
last_url = ""

#####################
# OpenAI Setup (New SDK style)
#####################
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

# We'll define a system prompt that tells GPT exactly how to respond.
SYSTEM_PROMPT = """Here is a massive URL that reflects how the URL gets created when you choose filters on our website. we're just looking at drivers rn. 

https://www.2ndswing.com/golf-clubs/drivers?g2_brand%5B0%5D=Cleveland&g2_brand%5B1%5D=Cobra&g2_brand%5B2%5D=Mizuno&g2_brand%5B3%5D=Ping&g2_brand%5B4%5D=TaylorMade&g2_brand%5B5%5D=Titleist&g2_club_desiredballflight%5B0%5D=Draw+Bias&g2_club_desiredballflight%5B1%5D=Draw%2FHook&g2_club_desiredballflight%5B2%5D=Fade%2CNeutral&g2_club_desiredballflight%5B3%5D=High+MOI&g2_club_desiredballflight%5B4%5D=Low+Spin+%2F+Fade&g2_club_desiredballflight%5B5%5D=Neutral&g2_club_length%5B0%5D=45.25in&g2_club_length%5B1%5D=45.5in&g2_club_length%5B2%5D=45.75in&g2_club_loft%5B0%5D=10.5%C2%B0&g2_club_loft%5B1%5D=10%C2%B0&g2_club_loft%5B2%5D=11%C2%B0&g2_club_loft%5B3%5D=12%C2%B0&g2_club_loft%5B4%5D=9.5%C2%B0&g2_condition%5B0%5D=Above+Average+9.0&g2_condition%5B1%5D=Average+8.0&g2_condition%5B2%5D=Below+Average+7.0&g2_condition%5B3%5D=Mint+9.5&g2_condition%5B4%5D=New&g2_dexterity%5B0%5D=Left+Handed&g2_dexterity%5B1%5D=Right+Handed&g2_locations%5B0%5D=Columbia&g2_locations%5B1%5D=Dallas&g2_locations%5B2%5D=Hub&g2_locations%5B3%5D=Minnetonka&g2_locations%5B4%5D=Scottsdale+%28S%29&g2_shaft_flex%5B0%5D=Regular&g2_shaft_flex%5B1%5D=Senior&g2_shaft_flex%5B2%5D=Stiff&g2_shaft_flex%5B3%5D=X-Stiff&new_used_filter%5B0%5D=New&new_used_filter%5B1%5D=Used&price=425-850

Keep in mind there are is 'condition' and 'new/used' filters. The URL above is just an example of how the URL gets built when you choose filters. If use specifies new or used, use the new_used_filter, but if they specify a more specific condition, use g2_condition.

This URL should act as an example for how to build URLs when certain filters are added or chosen. However I want to go a step further. I want to describe to you drivers, in natural language, that I'm looking for, and have you build a URL based on the example you saw. When I give you a request, you will respond ONLY with a url. Ready? 
"""

def get_url_from_llm(user_query: str) -> str:
    try:
        response = client.chat.completions.create(
            model="gpt-4o",  # or "gpt-3.5-turbo"
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_query}
            ],
            temperature=0
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print("OpenAI error:", e)
        return ""

def scrape_2ndswing(url: str):
    import requests
    from bs4 import BeautifulSoup

    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(r.text, "html.parser")

        products = soup.select("div.product-box.product-item-info")
        all_data = []

        for p in products:
            # IMAGE
            img_tag = p.find("img", class_="product-image-photo")
            img_url = img_tag["src"] if img_tag else ""

            # BRAND
            brand_div = p.find("div", class_="product-brand")
            brand = brand_div.get_text(strip=True) if brand_div else "N/A"

            # MODEL
            # (Single used clubs often have .pmp-product-category;
            #  Parent models might have .p-title instead.)
            model_div = p.find("div", class_="pmp-product-category")
            if model_div:
                model = model_div.get_text(strip=True)
            else:
                title_div = p.find("div", class_="p-title")
                model = title_div.get_text(strip=True) if title_div else "N/A"

            # URL
            # Typically in <a class="product photo product-item-photo" href="...">
            link_tag = p.select_one("a.product.photo.product-item-photo")
            product_url = link_tag["href"] if link_tag else ""

            # Check if new-configurable parent or single used
            is_parent_model = (
                p.get("data-itemhasused") == "1"
                and p.get("data-hasnewvariants") == "1"
            )

            if is_parent_model:
                # For parent model, show minimal info in your final UI
                all_data.append({
                    "brand": brand,
                    "model": model,
                    "img_url": img_url,
                    "url": product_url,
                    "price": None,
                    "condition": None,
                    "dexterity": None,
                    "loft": None,
                    "flex": None,
                    "shaft": None,
                    "parent_model": True
                })
                continue

            # If it's a single used club, parse all details
            price_div = p.find("div", class_="current-price")
            price = price_div.get_text(strip=True) if price_div else "N/A"

            condition = "N/A"
            dexterity = "N/A"
            loft = "N/A"
            flex = "N/A"
            shaft = "N/A"

            attr_block = p.find("div", class_="pmp-attribute")
            if attr_block:
                cond_div = attr_block.find("div", class_="pmp-product-condition")
                if cond_div:
                    condition = cond_div.get_text(strip=True)

                spans = attr_block.find_all("span", class_="pmp-attribute-label")
                for span in spans:
                    label = span.get_text(strip=True).rstrip(":")
                    value = span.next_sibling
                    while value and getattr(value, "name", None) == "br":
                        value = value.next_sibling

                    value_str = "N/A"
                    if value:
                        if isinstance(value, str):
                            value_str = value.strip()
                        else:
                            value_str = value.get_text(strip=True)

                    label_lower = label.lower()
                    if label_lower == "dexterity":
                        dexterity = value_str
                    elif label_lower == "loft":
                        loft = value_str
                    elif label_lower == "flex":
                        flex = value_str
                    elif label_lower == "shaft":
                        shaft = value_str

            all_data.append({
                "brand": brand,
                "model": model,
                "img_url": img_url,
                "url": product_url,
                "price": price,
                "condition": condition,
                "dexterity": dexterity,
                "loft": loft,
                "flex": flex,
                "shaft": shaft,
                "parent_model": False
            })

        return all_data

    except Exception as e:
        print("Scrape error:", e)
        return []




#####################
# SINGLE ROUTE
#####################
@app.route("/", methods=["GET", "POST"])
def index():
    global last_products, last_query, last_url

    if request.method == "POST":
        # User typed a new search
        user_query = request.form.get("user_query", "")

        # 1) GPT -> get URL
        generated_url = get_url_from_llm(user_query)

        # 2) Scrape
        product_data = scrape_2ndswing(generated_url)

        # 3) Stash in global vars
        last_query = user_query
        last_url = generated_url
        last_products = product_data

        # 4) Redirect so refreshing doesn't re-POST
        return redirect(url_for("index"))
    else:
        # GET request → show results if we have them
        # Then CLEAR so refresh empties the page
        local_query = last_query
        local_url = last_url
        local_products = last_products

        # Clear them out
        last_query = ""
        last_url = ""
        last_products = []

        return render_template_string(HTML_TEMPLATE,
            user_query=local_query,
            generated_url=local_url,
            products=local_products
        )

#####################
# HTML
#####################
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <title>Natural Language Golf Search</title>
    <!-- Make mobile screens behave properly -->
    <meta name="viewport" content="width=device-width, initial-scale=1.0">

    <style>
        /* GLOBAL RESET */
        * {
            box-sizing: border-box;
        }

        body {
            font-family: Arial, sans-serif;
            margin: 2em;
            position: relative;
            font-size: 16px;
        }

        /* FORM AREA */
        form { 
            margin-bottom: 1em; /* We'll add extra spacing below */
            display: flex; 
            flex-direction: column; 
            gap: 1em;
            max-width: 600px;
            margin: 0 auto; /* centers the form on larger screens */
        }
        .search-textarea {
            width: 100%;
            max-width: 100%;  /* ensures no overflow on mobile */
            min-height: 100px;
            padding: 0.8em;
            border-radius: 8px;
            border: 1px solid #ccc;
            resize: vertical;
            font-size: 1em;
        }
        .search-button {
            padding: 0.7em 1.2em;
            border: none;
            border-radius: 8px;
            background-color: #b71c1c;
            color: #fff;
            cursor: pointer;
            font-size: 1.1em;
            width: 160px;
            align-self: center;
        }
        .search-button:hover {
            background-color: #9a1616;
        }

        /* SPINNER OVERLAY */
        #spinner-overlay {
            display: none; /* hidden by default */
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background-color: rgba(255, 255, 255, 0.7);
            z-index: 9999;
        }
        #spinner {
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            text-align: center;
        }
        #spinner img {
            width: 64px; 
            height: 64px;
        }
        #spinner p {
            margin-top: 0.5em;
            font-weight: bold;
        }

        /* PRODUCT RESULTS */
        .product-grid {
            display: grid;
            /* We want auto‐fitting columns of at least 220px, but no more than 4 columns total */
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 1em;           /* spacing between columns/rows */
            max-width: 1000px;  /* ensures at most ~4 columns fit */
            margin: 0 auto;     /* center grid within the page */
            justify-items: center; /* optional, center tiles horizontally in their cells */
        }

        .tile {
            /* No need for fixed width; let grid handle it */
            border: 1px solid #ccc;
            border-radius: 6px;
            padding: 1em;
            text-align: center;
            background-color: #fff;
        }

        .tile img {
            max-width: 100%;
            height: auto;
            margin-bottom: 0.5em;
        }
        .price-text {
            color: #b71c1c;
            font-weight: bold;
            margin-bottom: 0.5em;
        }
        .attr {
            font-size: 0.9em;
            color: #444;
        }

        /* MAKE THE GENERATED URL WRAP & HAVE SPACE ABOVE IT */
        .generated-url {
            word-wrap: break-word;
            overflow-wrap: break-word;
            white-space: normal;
            margin: 2em auto 2em auto; /* 2em top margin for space, auto horizontally */
            max-width: 600px;         /* keep it from going edge to edge on large screens */
        }

        .generated-url a {
            color: #b71c1c;
            text-decoration: none; /* remove underlines if you'd like */
        }

        .generated-url a:hover {
            text-decoration: underline;
        }

        /* MOBILE RESPONSIVENESS */
        @media (max-width: 600px) {
            body {
                font-size: 18px; /* bigger text on smaller screens */
                margin: 1em;
            }
            .tile {
                width: 90%; /* tile goes full width on small screens */
            }
        }
    </style>

    <script>
        // Show the spinner overlay when user submits the form
        function showSpinner() {
            document.getElementById('spinner-overlay').style.display = 'block';
        }
    </script>
</head>
<body>
    <h1 style="text-align:center;">Natural Language Golf Search</h1>

    <!-- LOADING SPINNER -->
    <div id="spinner-overlay">
        <div id="spinner">
            <img src="https://media3.giphy.com/media/v1.Y2lkPTc5MGI3NjExdTN1bmc2d2o1dnM5dXBuNzNncmxqYTN0NDFydXVybGQ3cTRvYnhqNCZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/sSgvbe1m3n93G/giphy.gif" alt="Loading...">
            <p>Loading...</p>
        </div>
    </div>

    <!-- YOUR FORM -->
    <form method="POST" onsubmit="showSpinner()">
        <label for="user_query" style="font-weight:bold;">Enter Your Search:</label>
        <textarea
            id="user_query"
            name="user_query"
            class="search-textarea"
            placeholder="e.g. Titleist left-handed driver regular flex under $400"
        >{{ user_query }}</textarea>
        <button type="submit" class="search-button">Search</button>
    </form>

    <!-- WRAPPED URL WITH SPACING ABOVE -->
    {% if generated_url %}
        <div class="generated-url">
            <strong>Generated URL:</strong>
            <a href="{{ generated_url }}" target="_blank">{{ generated_url }}</a>
        </div>
    {% endif %}

    <!-- PRODUCT GRID -->
    {% if products and products|length > 0 %}
        <div class="product-grid">
            {% for product in products %}
                <div class="tile">
                    <a href="{{ product.url }}" target="_blank" style="text-decoration: none; color: inherit;">
                        <img src="{{ product.img_url }}" alt="Product Image">
                        <h3>{{ product.brand }} {{ product.model }}</h3>

                        {% if product.parent_model %}
                            <!-- If it's a parent model, just show "PARENT MODEL" -->
                            <div class="attr">
                                <p>PARENT MODEL</p>
                            </div>
                        {% else %}
                            <!-- Single used club: show price and attributes -->
                            <div class="price-text">{{ product.price }}</div>
                            <div class="attr">
                                <p>Condition: {{ product.condition }}</p>
                                <p>Dexterity: {{ product.dexterity }}</p>
                                <p>Loft: {{ product.loft }}</p>
                                <p>Flex: {{ product.flex }}</p>
                                <p>Shaft: {{ product.shaft }}</p>
                            </div>
                        {% endif %}
                    </a>
                </div>
            {% endfor %}
        </div>
    {% endif %}
</body>
</html>
"""


if __name__ == "__main__":
    # Run locally
    app.run(debug=True, port=5000)
