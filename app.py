import os
import json
from flask import Flask, request, redirect, url_for, render_template, jsonify, session
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import mixpanel

# Import our custom modules
from config import VISIBLE_ATTRS, PLACEHOLDERS, CLUB_PROMPT_FILES, RATE_LIMIT, FLASK_PORT, FLASK_DEBUG
from services.llm_service import classify_query_is_model_specific, extract_and_map_models, build_url_with_llm
from services.scraper import scrape_2ndswing

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-key-change-me")

# Rate limiting
limiter = Limiter(get_remote_address, app=app, default_limits=[RATE_LIMIT], storage_uri="memory://")

@app.route("/", methods=["GET", "POST"])
def index():
    # Track page view for all requests
    if os.environ.get("MIXPANEL_TOKEN"):
        mp = mixpanel.Mixpanel(os.environ.get("MIXPANEL_TOKEN"))
        mp.track(request.remote_addr, 'Page View', {
            'page': 'home',
            'method': request.method,
            'user_agent': request.headers.get('User-Agent', ''),
            'referrer': request.headers.get('Referer', '')
        })

    # Initialize default values
    user_query = ""
    generated_url = ""
    products = []
    club_type = "Driver"
    total_count = None
    use_new_architecture = False
    applied_filters = []
    next_page_url = None

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
        products, total_count, applied_filters, next_page_url = scrape_2ndswing(generated_url)

        # Track search with Mixpanel - exactly the 5 things requested
        if os.environ.get("MIXPANEL_TOKEN"):
            mp = mixpanel.Mixpanel(os.environ.get("MIXPANEL_TOKEN"))
            mp.track(request.remote_addr, 'Search Performed', {
                'club_type': club_type,                    # a) club type
                'user_query': user_query,                  # b) user's search query  
                'generated_url': generated_url,            # c) URL that's generated
                'applied_filters': applied_filters,        # d) filters used in search
                'product_count': total_count or 0          # e) number of products found
            })

        # Store results in session and redirect to avoid POST resubmission on refresh (PRG pattern)
        session['last_results'] = {
            'user_query': user_query,
            'generated_url': generated_url,
            'products': products,
            'club_type': club_type,
            'total_count': total_count,
            'use_new_architecture': use_new_architecture,
            'applied_filters': applied_filters,
            'next_page_url': next_page_url,
        }
        return redirect(url_for('index'))

    # For GET requests, if we have results stored from the previous POST, render them once then clear
    stored = session.pop('last_results', None)
    if stored:
        return render_template(
            "index.html",
            user_query=stored.get('user_query', ""),
            generated_url=stored.get('generated_url', ""),
            products=stored.get('products', []),
            club_type=stored.get('club_type', "Driver"),
            total_count=stored.get('total_count'),
            use_new_architecture=stored.get('use_new_architecture', False),
            applied_filters=stored.get('applied_filters', []),
            next_page_url=stored.get('next_page_url'),
            VISIBLE_ATTRS=VISIBLE_ATTRS,
            placeholders_json=json.dumps(PLACEHOLDERS)
        )

    # Default empty page render
    return render_template(
        "index.html",
        user_query=user_query,
        generated_url=generated_url,
        products=products,
        club_type=club_type,
        total_count=total_count,
        use_new_architecture=use_new_architecture,
        applied_filters=applied_filters,
        next_page_url=next_page_url,
        VISIBLE_ATTRS=VISIBLE_ATTRS,
        placeholders_json=json.dumps(PLACEHOLDERS)
    )


@app.route("/load_more", methods=["POST"])
@limiter.limit(RATE_LIMIT)
def load_more():
    """Load more products from the next page URL."""
    try:
        next_url = request.json.get("next_url")
        club_type = request.json.get("club_type", "Driver")
        
        if not next_url:
            return jsonify({"error": "No next URL provided"}), 400
            
        products, _, _, next_page_url = scrape_2ndswing(next_url)
        
        return jsonify({
            "products": products,
            "next_page_url": next_page_url,
            "club_type": club_type
        })
        
    except Exception as e:
        print("Load more error:", e)
        return jsonify({"error": "Failed to load more products"}), 500

if __name__ == "__main__":
    app.run(debug=FLASK_DEBUG, port=FLASK_PORT)
