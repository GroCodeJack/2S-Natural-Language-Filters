import os
from urllib.parse import quote_plus
from flask import Flask, request, redirect, url_for, render_template_string
from openai import OpenAI
import requests
from bs4 import BeautifulSoup
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import glob, json 

app = Flask(__name__)

# Uncomment to re‑enable rate limiting
limiter = Limiter(get_remote_address, app=app, default_limits=["350 per hour"], storage_uri="memory://")

# ------- GLOBAL STATE (simple demo cache) ------- #
last_products: list = []
last_query: str = ""
last_url: str = ""
last_club_type: str = ""
last_total = None

# --------------- OPENAI --------------- #
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

# ---------- PROMPT FILES (by club) ---------- #
club_prompt_files = {
    "Driver": "driver.txt",
    "Fairway Woods": "fairway.txt",
    "Hybrids": "hybrid.txt",
    "Iron Sets": "ironset.txt",
    "Wedges": "wedge.txt",
    "Putters": "putter.txt",
    "Single Irons": "singleiron.txt",
}

# ---------- WHICH ATTRIBUTES TO SHOW ---------- #
VISIBLE_ATTRS = {
    "Driver":        ["dexterity", "loft", "flex", "shaft"],
    "Fairway Woods": ["dexterity", "type", "loft", "flex", "shaft"],
    "Hybrids":       ["dexterity", "type", "loft", "flex", "shaft"],
    "Iron Sets":     ["dexterity", "makeup", "material", "flex", "shaft"],
    "Wedges":        ["dexterity", "type", "loft", "bounce", "flex", "shaft"],
    "Single Irons":  ["dexterity", "type", "material", "flex", "shaft"],
    "Putters":       ["dexterity", "length"],
}

def load_placeholders():
    bank = {}
    for path in glob.glob("textdocs/placeholder-text/*.txt"):
        key = os.path.splitext(os.path.basename(path))[0]   # driver, fairway…
        with open(path, encoding="utf-8") as f:
            bank[key] = [ln.strip() for ln in f if ln.strip()]
    return bank

PLACEHOLDERS = load_placeholders()

# ----------------------------------------------------------------------------
# STEP 1 – CLASSIFY WHETHER QUERY IS MODEL‑SPECIFIC
# ----------------------------------------------------------------------------

def classify_query_is_model_specific(user_query: str) -> bool:
    """Return True if the query references explicit club models."""
    try:
        with open(os.path.join("textdocs", "brandlist.txt"), encoding="utf‑8") as f:
            brand_list = f.read().strip()
    except Exception as e:
        print("Error reading brandlist.txt:", e)
        brand_list = ""

    examples = (
        "EXAMPLES – respond ONLY with 1 or 0\n"
        'User: "ping irons"                  → 0\n'
        'User: "titleist drivers"            → 0\n'
        'User: "ping g430 driver"            → 1\n'
        'User: "taylormade spider putters"   → 1\n'
        'User: "mizuno jpx 923 forged"       → 1'
    )

    system_prompt = (
        "You are the first step in a natural‑language golf‑search tool. "
        "Reply with '1' if the query is model‑specific or '0' if generic. "
        "Never output anything except '1' or '0'.\n\n" + examples + "\n\n" +
        "These names are BRANDS, not models – do *not* treat them as models:\n" + brand_list
    )

    try:
        resp = client.chat.completions.create(
            model="gpt-4.1",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_query},
            ],
            temperature=0,
            max_tokens=2,
        )
        result = resp.choices[0].message.content.lstrip()[:1]
        print(f"[DEBUG] classification result: {result}")
        return result == "1"
    except Exception as e:
        print("OpenAI classification error:", e)
        return False

# ----------------------------------------------------------------------------
# STEP 2 – EXTRACT & MAP MODELS
# ----------------------------------------------------------------------------

def extract_and_map_models(user_query: str, club_type: str) -> str:
    """Return comma‑separated pairs userReference=OfficialName (≤7)."""
    file_map = {
        "Driver": "drivers.txt",
        "Fairway Woods": "fairways.txt",
        "Hybrids": "hybrids.txt",
        "Iron Sets": "ironsets.txt",
        "Wedges": "wedges.txt",
        "Putters": "putters.txt",
        "Single Irons": "singleirons.txt",
    }
    try:
        with open(os.path.join("model_data", file_map.get(club_type, "drivers.txt")), "r") as f:
            model_list = f.read().strip()
    except Exception as e:
        print("Error reading model_data file:", e)
        model_list = ""

    system_prompt = f"""
You identify {club_type} model names in the user's query and map them to the official list below.
Return pairs in the format userReference=officialModel, comma‑separated, max 7.
List of official models:
{model_list}
"""
    try:
        resp = client.chat.completions.create(
            model="gpt-4.1",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_query},
            ],
            temperature=0,
            max_tokens=400,
        )
        out = resp.choices[0].message.content.strip()
        print(f"[DEBUG] extraction+mapping output: {out}")
        return out
    except Exception as e:
        print("OpenAI extraction error:", e)
        return ""

# ----------------------------------------------------------------------------
# STEP 3 – BUILD URL (we control g2_model params deterministically)
# ----------------------------------------------------------------------------

def build_url_with_llm(user_query: str, system_prompt: str, mapped_models: str) -> str:
    # ---- 1. Build model filter chunk ourselves ---- #
    model_chunk = ""
    if mapped_models:
        names = [pair.split("=", 1)[1].strip() for pair in mapped_models.split(",") if "=" in pair]
        seen, uniq = set(), []
        for n in names:
            if n not in seen:
                seen.add(n)
                uniq.append(n)
            if len(uniq) == 7:
                break
        model_chunk = "".join(f"&g2_model[{i}]={quote_plus(name)}" for i, name in enumerate(uniq))

    llm_prompt = system_prompt + "\n\nDo NOT include any g2_model parameters; they will be appended later."

    try:
        resp = client.chat.completions.create(
            model="gpt-4.1",
            messages=[
                {"role": "system", "content": llm_prompt},
                {"role": "user", "content": user_query},
            ],
            temperature=0,
            max_tokens=400,
        )
        base_url = resp.choices[0].message.content.strip()
    except Exception as e:
        print("OpenAI URL‑building error:", e)
        return ""

    if model_chunk:
        sep = "&" if "?" in base_url and not base_url.endswith("&") else ""
        final_url = f"{base_url}{sep}{model_chunk.lstrip('&')}" if "?" in base_url else f"{base_url}?{model_chunk.lstrip('&')}"
    else:
        final_url = base_url
    return final_url

# ----------------------------------------------------------------------------
# STEP 4 – SCRAPE 2ND SWING
# ----------------------------------------------------------------------------

def scrape_2ndswing(url: str):
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        soup = BeautifulSoup(requests.get(url, headers=headers, timeout=10).text, "html.parser")
        all_data = []
        total_count = None
        # capture total count
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

            # --- capture ALL attrs dynamically --- #
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

            # price & condition (if single‑used)
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

# ----------------------------------------------------------------------------
# FLASK ROUTE
# ----------------------------------------------------------------------------
@app.route("/", methods=["GET", "POST"])
def index():
    global last_products, last_query, last_url, last_club_type, last_total

    if request.method == "POST":
        user_query = request.form.get("user_query", "")
        club_type = request.form.get("club_type", "Driver")

        mapped_models = extract_and_map_models(user_query, club_type) if classify_query_is_model_specific(user_query) else ""

        prompt_path = os.path.join("textdocs", "prompts", club_prompt_files.get(club_type, "driver.txt"))
        try:
            with open(prompt_path, "r") as f:
                system_prompt = f.read()
        except Exception:
            system_prompt = "Build a URL for the chosen club type."

        generated_url = build_url_with_llm(user_query, system_prompt, mapped_models)
        product_data, total_count = scrape_2ndswing(generated_url)

        last_query, last_url, last_products, last_club_type, last_total = user_query, generated_url, product_data, club_type, total_count
        return redirect(url_for("index"))

    # GET → render results then clear cache
    local_query, local_url, local_products, local_type, local_total = last_query, last_url, last_products, last_club_type, last_total
    last_query = last_url = last_club_type = ""; last_products = []; last_total = None

    return render_template_string(HTML_TEMPLATE,
                                  user_query=local_query,
                                  generated_url=local_url,
                                  products=local_products,
                                  club_type=local_type,
                                  total_count=local_total,
                                  VISIBLE_ATTRS=VISIBLE_ATTRS,
                                  placeholders_json=json.dumps(PLACEHOLDERS))


# ----------------------------------------------------------------------------
# INLINE HTML TEMPLATE
# ----------------------------------------------------------------------------
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <title>Natural Language Golf Search</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">

    <style>
        .result-count { font-weight:600; margin:1em auto; max-width:1000px; }
        /* ---------- RESET ---------- */
        * { box-sizing: border-box; }

        body {
            font-family: 'urw-din', sans-serif;
            margin: 2em;
            font-size: 16px;
        }

        /* ---------- FORM ---------- */
        form {
            margin-bottom: 1em;
            display: flex;
            flex-direction: column;
            gap: 1em;
            max-width: 600px;
            margin: 0 auto;
        }

        #club_type {
            padding: 0.6em 1em;
            min-width: 200px;
            border-radius: 8px;
            font-size: 1em;
        }

        .search-textarea {
            min-height: 100px;
            padding: 0.8em;
            border-radius: 8px;
            border: 1px solid #ccc;
            resize: vertical;
            font-size: 1em;
        }

        :root {
            --ph-opacity: 1;                /* placeholder fully visible by default */
        }

        .search-textarea::placeholder {
            opacity: var(--ph-opacity);
            transition: opacity 0.25s ease; /* animate only the placeholder text */
            color: #888;
        }


        .search-button {
            padding: 0.7em 1.2em;
            border: none;
            border-radius: 8px;
            background: #b71c1c;
            color: #fff;
            cursor: pointer;
            width: 160px;
            align-self: center;
        }

        /* ---------- PRODUCT GRID ---------- */
        .product-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 1em;
            max-width: 1000px;
            margin: 0 auto;
        }

        .tile {
            border: 1px solid #ccc;
            border-radius: 6px;
            padding: 1em;
            text-align: center;
            background: #fff;

            /* fade-in setup */
            opacity: 0;
            transform: translateY(10px);
            transition: opacity 0.4s ease, transform 0.4s ease, box-shadow 0.4s ease;
        }

        .tile.fade-in {
            opacity: 1;
            transform: translateY(0);
        }

        .tile:hover {
            transform: translateY(-6px);
            box-shadow: 0 8px 16px rgba(0,0,0,0.15);
        }

        .tile img {
            width: 100%;
            max-height: 160px;
            object-fit: contain;
            margin-bottom: 0.5em;
        }

        .price-text {
            color: #b71c1c;
            font-weight: bold;
            margin-bottom: 0.5em;
        }

        .attr { font-size: 0.9em; color: #444; }

        /* ---------- GENERATED URL ---------- */
        .generated-url {
            word-wrap: break-word;
            max-width: 600px;
            margin: 2em auto;
        }
        .generated-url a { color:#b71c1c; text-decoration:none; }
        .generated-url a:hover { text-decoration:underline; }

        /* ---------- LOADER ---------- */
        @keyframes spin {
            0%   { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }

        .spinner-img {
            width: 90px;
            height: 90px;
            animation: spin 1.3s linear infinite;
        }
    </style>

    <script>
        /* ---------- SPINNER ---------- */
        function showSpinner() {
            document.getElementById('spinner-overlay').style.display = 'block';
        }

        /* ---------- PLACEHOLDER ROTATOR ---------- */
        document.addEventListener('DOMContentLoaded', () => {
            const BANKS = JSON.parse('{{ placeholders_json|safe }}');

            // map dropdown text → placeholder file slug
            const SLUG = {
                'Driver':        'driver',
                'Fairway Woods': 'fairway',
                'Hybrids':       'hybrid',
                'Iron Sets':     'ironset',
                'Wedges':        'wedge',
                'Putters':       'putter',
                'Single Irons':  'singleiron'
            };

            let idx = 0;

            function updatePh() {
                const sel = document.getElementById('club_type');
                const ta  = document.getElementById('user_query');
                const key = SLUG[sel.value] || 'driver';
                const arr = BANKS[key] || [];
                if (!arr.length) return;

                /* fade placeholder out */
                ta.style.setProperty('--ph-opacity', '0');

                setTimeout(() => {
                    ta.placeholder = arr[idx % arr.length];   // swap text
                    ta.style.setProperty('--ph-opacity', '1'); // fade back in
                    idx = (idx + 1) % arr.length;
                }, 250);  // matches the CSS 0.25 s
            }


            updatePh();                     // initial
            setInterval(updatePh, 5000);    // rotate

            document.getElementById('club_type')
                    .addEventListener('change', () => { idx = 0; updatePh(); });
        });
            document.addEventListener("DOMContentLoaded", () => {
            const textarea = document.getElementById("user_query");
            const form = textarea.closest("form");

            textarea.addEventListener("keydown", function(e) {
                if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();  // prevent newline
                    showSpinner();       // show spinner
                    form.submit();       // trigger the form submission
                }
            });
        });
        /* ---------- TILE FADE-IN ---------- */
        document.addEventListener('DOMContentLoaded', () => {
            const tiles = document.querySelectorAll('.tile');
            tiles.forEach((tile, idx) => {
                setTimeout(() => {
                    tile.classList.add('fade-in');
                }, idx * 80);     // stagger by 80 ms per tile
            });
        });
    </script>
</head>

<body>
    <div style="text-align:center; margin-bottom:0.5em;">
        <img src="https://i.postimg.cc/nrSJ8C3T/2s-nls-logo.png"
             alt="2S Natural Language Golf Search"
             style="max-width:260px;width:60%;height:auto;">
    </div>
    <h3 style="text-align:center; font-family:'urw-din',sans-serif; font-weight:400; font-style:normal;">Enter your search in plain English and let us do the rest!</h3>

    <!-- ---------- LOADING SPINNER ---------- -->
    <div id="spinner-overlay"
         style="display:none;position:fixed;top:0;left:0;width:100%;height:100%;
                background:rgba(255,255,255,0.7);z-index:9999;">
        <div style="position:absolute;top:50%;left:50%;transform:translate(-50%, -50%);
                    text-align:center;">
            <img src="https://i.postimg.cc/yxqzbNFM/spinner.png" class="spinner-img" alt="Loading spinner">
            <p>Loading...</p>
        </div>
    </div>

    <!-- ---------- SEARCH FORM ---------- -->
    <form method="POST" onsubmit="showSpinner()">
        <label for="club_type"><strong>Select Club Type:</strong></label>
        <select id="club_type" name="club_type">
            {% for ct in VISIBLE_ATTRS.keys() %}
                <option value="{{ ct }}" {% if club_type == ct %}selected{% endif %}>{{ ct }}</option>
            {% endfor %}
        </select>

        <label for="user_query"><strong>Enter Your Search:</strong></label>
        <textarea id="user_query"
                  name="user_query"
                  class="search-textarea"
                  placeholder="e.g. Titleist left-handed driver regular flex under $400">{{ user_query }}</textarea>

        <button type="submit" class="search-button">Search</button>
    </form>

    <!-- ---------- GENERATED URL ---------- -->
    {% if generated_url %}
        <div class="generated-url">
            <strong>Generated URL:</strong>
            <a href="{{ generated_url }}" target="_blank">{{ generated_url }}</a>
        </div>
    {% endif %}

    <!-- ---------- RESULTS INFO ---------- -->
    {% if total_count %}
        <div class="result-count">Total products found: {{ total_count }}</div>
    {% endif %}

    <!-- ---------- RESULTS GRID ---------- -->
    {% if products %}
        <div class="product-grid">
            {% for product in products %}
                <div class="tile">
                    <a href="{{ product.url }}" target="_blank" style="text-decoration:none;color:inherit;">
                        <img src="{{ product.img_url }}" alt="Product Image">
                        <h3>{{ product.brand }} {{ product.model }}</h3>

                        {% if product.parent_model %}
                            <div class="attr"><p>PARENT MODEL</p></div>
                        {% else %}
                            <div class="price-text">{{ product.price }}</div>
                            <div class="attr">
                                <p>Condition: {{ product.condition }}</p>
                                {% for key in VISIBLE_ATTRS.get(club_type, []) %}
                                    {% if product.attrs.get(key) %}
                                        <p>{{ key|capitalize }}: {{ product.attrs[key] }}</p>
                                    {% endif %}
                                {% endfor %}
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
    app.run(debug=True, port=5000)
