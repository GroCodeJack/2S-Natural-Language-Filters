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
            model="gpt-4o-mini",  # or "gpt-3.5-turbo"
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
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(r.text, "html.parser")

        products = soup.select("div.product-box.product-item-info")
        all_data = []

        for p in products:
            img_tag = p.find("img", class_="product-image-photo")
            img_url = img_tag["src"] if img_tag else ""

            brand_div = p.find("div", class_="product-brand")
            brand = brand_div.get_text(strip=True) if brand_div else "N/A"

            model_div = p.find("div", class_="pmp-product-category")
            model = model_div.get_text(strip=True) if model_div else "N/A"

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

                    if label.lower() == "dexterity":
                        dexterity = value_str
                    elif label.lower() == "loft":
                        loft = value_str
                    elif label.lower() == "flex":
                        flex = value_str
                    elif label.lower() == "shaft":
                        shaft = value_str

            all_data.append({
                "brand": brand,
                "model": model,
                "price": price,
                "img_url": img_url,
                "condition": condition,
                "dexterity": dexterity,
                "loft": loft,
                "flex": flex,
                "shaft": shaft
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
    <style>
        body {
            font-family: Arial, sans-serif;
            margin: 2em;
            position: relative;
        }
        form { 
            margin-bottom: 2em; 
            display: flex; 
            flex-direction: column; 
            gap: 1em;
            max-width: 600px;
        }
        .search-textarea {
            width: 100%;
            min-height: 100px; 
            padding: 0.5em;
            border-radius: 8px;
            border: 1px solid #ccc;
            resize: vertical;
        }
        .search-button {
            padding: 0.6em 1em;
            border: none;
            border-radius: 8px;
            background-color: #b71c1c;
            color: #fff;
            cursor: pointer;
            font-size: 1em;
            width: 150px;
        }
        .search-button:hover {
            background-color: #9a1616;
        }

        .generated-url {
            width: 100%;
            word-wrap: break-word;        /* old fallback */
            overflow-wrap: break-word;    /* standard property */
            white-space: normal;          /* ensure wrapping is allowed */
        }

            .generated-url a {
            text-decoration: none; 
            color: #0066cc;               /* or whatever color you want */
            word-wrap: break-word;        
            overflow-wrap: break-word;    
            white-space: normal;
        }


        /* LOADING SPINNER OVERLAY */
        #spinner-overlay {
            display: none;
            position: fixed;
            top: 0; left: 0;
            width: 100%; height: 100%;
            background-color: rgba(255, 255, 255, 0.7);
            z-index: 9999;
        }
        #spinner {
            position: absolute;
            top: 50%; left: 50%;
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

        .product-grid {
            display: flex; 
            flex-wrap: wrap;
        }
        .tile {
            border: 1px solid #ccc;
            border-radius: 6px;
            padding: 1em;
            margin: 1em;
            width: 250px;
            text-align: center;
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

        @media (max-width: 600px) {
            .product-grid {
                flex-direction: column;
                align-items: center;
            }
            .tile {
                width: 90%;
            }
        }
    </style>
    <script>
        function showSpinner() {
            document.getElementById('spinner-overlay').style.display = 'block';
        }
    </script>
</head>
<body>
    <h1>Natural Language Golf Search</h1>

    <div id="spinner-overlay">
      <div id="spinner">
        <img src="https://media.giphy.com/media/3oz8xIsloV7zOmt81G/giphy.gif" alt="Loading...">
        <p>Loading...</p>
      </div>
    </div>

    <!-- Single form for everything -->
    <form method="POST" onsubmit="showSpinner()">
        <label for="user_query">Enter Your Search:</label>
        <textarea 
            id="user_query" 
            name="user_query" 
            class="search-textarea"
            placeholder="e.g. Titleist left-handed driver regular flex under $400"
        >{{ user_query }}</textarea>

        <button type="submit" class="search-button">Search</button>
    </form>

    {% if generated_url %}
        <div class="generated-url">
            <strong>Generated URL:</strong>
        <a href="{{ generated_url }}" target="_blank">{{ generated_url }}</a>
    </div>
    {% endif %}

    {% if products and products|length > 0 %}
        <div class="product-grid">
        {% for product in products %}
            <div class="tile">
                <img src="{{ product.img_url }}" alt="Product Image">
                <h3>{{ product.brand }} {{ product.model }}</h3>
                <div class="price-text">{{ product.price }}</div>
                <div class="attr">
                    <p>Condition: {{ product.condition }}</p>
                    <p>Dexterity: {{ product.dexterity }}</p>
                    <p>Loft: {{ product.loft }}</p>
                    <p>Flex: {{ product.flex }}</p>
                    <p>Shaft: {{ product.shaft }}</p>
                </div>
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
