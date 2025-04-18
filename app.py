import os
from flask import Flask, request, redirect, url_for, render_template_string
from openai import OpenAI
import requests
from bs4 import BeautifulSoup
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address


app = Flask(__name__)

limiter = Limiter(
    get_remote_address,   # 1st positional argument = key_func
    app=app,              # Pass the Flask app as a named argument
    default_limits=["50 per hour"],
    storage_uri="memory://"
)

# We'll store results in these globals to keep it easy.
last_products = []
last_query = ""
last_url = ""
last_club_type = ""

#####################
# OPENAI SETUP
#####################
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

#####################
# MAP CLUB TYPE → PROMPT FILE
#####################
club_prompt_files = {
    "Driver": "driver.txt",
    "Fairway Woods": "fairway.txt",
    "Hybrids": "hybrid.txt",
    "Iron Sets": "ironset.txt",
    "Wedges": "wedge.txt",
    "Putters": "putter.txt",
    "Single Irons": "singleiron.txt"
}

#####################
# STEP 1: CLASSIFICATION
#####################
def classify_query_is_model_specific(user_query: str) -> bool:
    """
    Uses a lightweight LLM to determine if the user is specifying
    particular club models (return True) or is generic (False).
    Expects the LLM to respond with '1' or '0' only.
    """
    system_prompt = (
        "You are the first step in a natural language search tool whose purpose is "
        "to decide whether the user's query is asking about specific golf club models, "
        "or is more generic. If you detect a model-specific query, respond '1'. "
        "Otherwise respond '0'. NEVER provide any text besides '1' or '0'."
    )
    try:
        response = client.chat.completions.create(
            model="gpt-4.1",  # or any small classification model
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_query}
            ],
            temperature=0
        )
        classification = response.choices[0].message.content.strip()
        # Debug
        print(f"[DEBUG] classification result: {classification}")
        return (classification == "1")
    except Exception as e:
        print("OpenAI classification error:", e)
        return False

#####################
# STEP 2: EXTRACTION + MAPPING
#####################
def extract_and_map_models(user_query: str, club_type: str) -> str:
    """
    If the first LLM decides the query is model-specific, we call this function.
    It uses a second LLM to:
    1. Identify any model references in the user query,
    2. Map them to the official model names from our local /model_data/ file,
    3. Return a single line of comma-separated pairs like:
         userReference=officialModelName, userReference=officialModelName,...
       Or an empty string if nothing is confidently matched.
    """

    # Load the official model list from /model_data/<club_type>.txt
    folder = "model_data"
    file_map = {
        "Driver": "drivers.txt",
        "Fairway Woods": "fairways.txt",
        "Hybrids": "hybrids.txt",
        "Iron Sets": "ironsets.txt",
        "Wedges": "wedges.txt",
        "Putters": "putters.txt",
        "Single Irons": "singleirons.txt"
    }
    model_filename = file_map.get(club_type, "drivers.txt")
    path = os.path.join(folder, model_filename)

    try:
        with open(path, "r") as f:
            model_list = f.read().strip()
    except Exception as e:
        print("Error reading model_data file:", e)
        model_list = ""  # fallback if file not found

    # Build system prompt for the extraction+mapping LLM
    system_prompt = f"""
You are an assistant specializing in identifying golf club {club_type} model names 
within a user's query and mapping them to an official list of known models.

Instructions:
1. Read the user's query and find all references to specific model names or series.
2. Compare each reference to the provided list of known club models (below).
3. Find the best possible match for each reference (even if the user uses partial names, abbreviations, or slightly different wording).
4. For every reference you can confidently match, output the pair in the format: userReference=officialModelName
5. Separate multiple pairs by commas—no other punctuation or text is allowed.
6. If you cannot confidently match a reference to any official model name, omit it.
7. Your final response must be a single line, containing only these comma-separated pairs, and nothing else.

List of official {club_type} models:
{model_list}

Now respond based on the user's input.
""".strip()

    try:
        response = client.chat.completions.create(
            model="gpt-4.1",  # or whichever model you prefer
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_query}
            ],
            temperature=0
        )
        mapped_output = response.choices[0].message.content.strip()
        print(f"[DEBUG] extraction+mapping output: {mapped_output}")
        return mapped_output
    except Exception as e:
        print("OpenAI extraction error:", e)
        return ""

#####################
# STEP 3: URL-BUILDING
#####################
def build_url_with_llm(user_query: str, system_prompt: str, mapped_models: str, club_type: str) -> str:
    """
    The final step: pass the original (untouched) user query plus any extracted model data
    into the system prompt that constructs the final URL.
    We do NOT modify user_query. We simply provide mapped_models separately as extra context.
    """

    additional_instructions = ""
    if mapped_models.strip():
        additional_instructions = (
            f"\n\nBelow is a list of mapped models relevant to this query:\n{mapped_models}\n"
            "Use them to set the g2_model filters in the final URL."
        )

    # Combine the main system prompt with the extra instructions
    final_system_prompt = system_prompt + additional_instructions

    try:
        response = client.chat.completions.create(
            model="gpt-4.1",  # or "gpt-3.5-turbo", etc.
            messages=[
                # The system prompt with appended mapped_models context
                {"role": "system", "content": final_system_prompt},
                # The user's original query remains untouched
                {"role": "user", "content": user_query}
            ],
            temperature=0
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print("OpenAI URL-building error:", e)
        return ""

#####################
# SCRAPING 2ND SWING
#####################
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
            model_div = p.find("div", class_="pmp-product-category")
            if model_div:
                model = model_div.get_text(strip=True)
            else:
                title_div = p.find("div", class_="p-title")
                model = title_div.get_text(strip=True) if title_div else "N/A"

            # URL
            link_tag = p.select_one("a.product.photo.product-item-photo")
            product_url = link_tag["href"] if link_tag else ""

            # Check if new-configurable parent or single used
            is_parent_model = (
                p.get("data-itemhasused") == "1" and
                p.get("data-hasnewvariants") == "1"
            )

            if is_parent_model:
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

            # Single used club
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
# MAIN FLASK ROUTE
#####################
@app.route("/", methods=["GET", "POST"])
def index():
    global last_products, last_query, last_url, last_club_type

    if request.method == "POST":
        # 1) Grab user input
        user_query = request.form.get("user_query", "")
        club_type = request.form.get("club_type", "Driver")

        # STEP 1: CLASSIFICATION
        is_model_specific = classify_query_is_model_specific(user_query)

        # STEP 2: EXTRACTION + MAPPING (only if it's model-specific)
        mapped_models = ""
        if is_model_specific:
            mapped_models = extract_and_map_models(user_query, club_type)

        # STEP 3: URL-BUILDING
        # Load correct system prompt for this club type
        prompt_filename = club_prompt_files.get(club_type, "driver.txt")
        prompt_path = os.path.join("textdocs", "prompts", prompt_filename)

        try:
            with open(prompt_path, "r") as f:
                system_prompt = f.read()
        except Exception as e:
            print("Error reading prompt file:", e)
            system_prompt = "Build a URL for the chosen club type."

        # Build the final URL using the unmodified user query + mapped models
        generated_url = build_url_with_llm(
            user_query=user_query,
            system_prompt=system_prompt,
            mapped_models=mapped_models,
            club_type=club_type
        )

        # Scrape the final URL
        product_data = scrape_2ndswing(generated_url)

        # Store results in globals
        last_query = user_query
        last_url = generated_url
        last_products = product_data
        last_club_type = club_type

        return redirect(url_for("index"))

    else:
        # GET request: show results if we have them
        local_query = last_query
        local_url = last_url
        local_products = last_products
        local_club_type = last_club_type

        # Clear them out so refresh doesn’t re-show same data
        last_query = ""
        last_url = ""
        last_products = []
        last_club_type = ""

        # Render your template below...
        return render_template_string(
            HTML_TEMPLATE,  # Insert your existing HTML_TEMPLATE here
            user_query=local_query,
            generated_url=local_url,
            products=local_products,
            club_type=local_club_type
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
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 1em;
            max-width: 1000px;
            margin: 0 auto;
            justify-items: center;
        }

        .tile {
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

        .generated-url {
            word-wrap: break-word;
            overflow-wrap: break-word;
            white-space: normal;
            margin: 2em auto 2em auto;
            max-width: 600px;
        }

        .generated-url a {
            color: #b71c1c;
            text-decoration: none;
        }

        .generated-url a:hover {
            text-decoration: underline;
        }

        /* MOBILE RESPONSIVENESS */
        @media (max-width: 600px) {
            body {
                font-size: 18px;
                margin: 1em;
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
    <p style="text-align:center;">Enter your search in plain English and let us do the rest!</p>

    <!-- LOADING SPINNER -->
    <div id="spinner-overlay">
        <div id="spinner">
            <img src="https://media3.giphy.com/media/sSgvbe1m3n93G/giphy.gif" alt="Loading...">
            <p>Loading...</p>
        </div>
    </div>

    <!-- SEARCH FORM -->
    <form method="POST" onsubmit="showSpinner()">
        <label for="club_type" style="font-weight:bold;">Select Club Type:</label>
        <select id="club_type" name="club_type">
            <option value="Driver" {% if club_type == "Driver" %}selected{% endif %}>Driver</option>
            <option value="Fairway Woods" {% if club_type == "Fairway Woods" %}selected{% endif %}>Fairway Woods</option>
            <option value="Hybrids" {% if club_type == "Hybrids" %}selected{% endif %}>Hybrids</option>
            <option value="Iron Sets" {% if club_type == "Iron Sets" %}selected{% endif %}>Iron Sets</option>
            <option value="Wedges" {% if club_type == "Wedges" %}selected{% endif %}>Wedges</option>
            <option value="Putters" {% if club_type == "Putters" %}selected{% endif %}>Putters</option>
            <option value="Single Irons" {% if club_type == "Single Irons" %}selected{% endif %}>Single Irons</option>
        </select>

        <label for="user_query" style="font-weight:bold;">Enter Your Search:</label>
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
                <a href="{{ product.url }}" target="_blank" style="text-decoration: none; color: inherit;">
                    <img src="{{ product.img_url }}" alt="Product Image">
                    <h3>{{ product.brand }} {{ product.model }}</h3>
                    {% if product.parent_model %}
                        <div class="attr">
                            <p>PARENT MODEL</p>
                        </div>
                    {% else %}
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
