import os
import json
from flask import Flask, request, redirect, url_for, render_template
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Import our custom modules
from config import VISIBLE_ATTRS, PLACEHOLDERS, CLUB_PROMPT_FILES, RATE_LIMIT, FLASK_PORT, FLASK_DEBUG
from services.llm_service import classify_query_is_model_specific, extract_and_map_models, build_url_with_llm
from services.scraper import scrape_2ndswing

app = Flask(__name__)

# Rate limiting
limiter = Limiter(get_remote_address, app=app, default_limits=[RATE_LIMIT], storage_uri="memory://")

# Global state (simple demo cache)
last_products: list = []
last_query: str = ""
last_url: str = ""
last_club_type: str = ""
last_total = None
last_use_new_architecture: bool = False

@app.route("/", methods=["GET", "POST"])
def index():
    global last_products, last_query, last_url, last_club_type, last_total, last_use_new_architecture

    if request.method == "POST":
        user_query = request.form.get("user_query", "")
        club_type = request.form.get("club_type", "Driver")
        use_new_architecture = request.form.get("use_new_architecture") == "on"

        # Check if query is model-specific
        is_model_specific = classify_query_is_model_specific(user_query)

        # Determine prompt directory based on architecture selection
        prompt_dir = "prompts_v2" if use_new_architecture else "prompts_v1"
        
        # Handle model extraction based on architecture
        mapped_models = ""
        if use_new_architecture:
            # New architecture: skip model extraction for ALL club types (use q= parameter instead)
            pass
        else:
            # Old architecture: extract models for all model-specific queries
            if is_model_specific:
                mapped_models = extract_and_map_models(user_query, club_type)

        # Load system prompt for the club type from appropriate directory
        prompt_path = os.path.join("textdocs", prompt_dir, CLUB_PROMPT_FILES.get(club_type, "driver.txt"))
        try:
            with open(prompt_path, "r") as f:
                system_prompt = f.read()
        except Exception:
            system_prompt = "Build a URL for the chosen club type."

        # For new architecture, prepend classifier result for all club types
        if use_new_architecture:
            prefix = (
                f"CLASSIFICATION: {'MODEL_SPECIFIC' if is_model_specific else 'GENERIC'}\n"
                f"CLUB_TYPE: {club_type}\n"
            )
            system_prompt = prefix + system_prompt

        # Generate URL and scrape data
        generated_url = build_url_with_llm(user_query, system_prompt, mapped_models)
        product_data, total_count = scrape_2ndswing(generated_url)

        # Update global state
        last_query = user_query
        last_url = generated_url
        last_products = product_data
        last_club_type = club_type
        last_total = total_count
        last_use_new_architecture = use_new_architecture
        
        return redirect(url_for("index"))

    # GET request - render results and clear cache
    local_query = last_query
    local_url = last_url
    local_products = last_products
    local_type = last_club_type
    local_total = last_total
    local_use_new_arch = last_use_new_architecture
    
    # Clear cache
    last_query = last_url = last_club_type = ""
    last_products = []
    last_total = None
    last_use_new_architecture = False

    return render_template("index.html",
                          user_query=local_query,
                          generated_url=local_url,
                          products=local_products,
                          club_type=local_type,
                          total_count=local_total,
                          use_new_architecture=local_use_new_arch,
                          VISIBLE_ATTRS=VISIBLE_ATTRS,
                          placeholders_json=json.dumps(PLACEHOLDERS))

if __name__ == "__main__":
    app.run(debug=FLASK_DEBUG, port=FLASK_PORT)
