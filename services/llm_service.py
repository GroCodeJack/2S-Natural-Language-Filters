import os
from urllib.parse import quote_plus
from openai import OpenAI
from config import OPENAI_MODEL, MODEL_DATA_FILES, DEBUG_DUMP_SYSTEM_PROMPT, CLASSIFICATION_MODEL, EXTRACTION_MODEL, URL_BUILDING_MODEL

# Initialize OpenAI client
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

CLUB_TYPE_KEYWORDS = {
    "Driver": ["driver", "drivers", "drive"],
    "Fairway Woods": [
        "fairway", "fairways", "wood", "woods",
        "3w", "4w", "5w", "6w", "7w", "8w", "9w", "10w", "11w",
    ],
    "Hybrids": ["hybrid", "hybrids"],
    "Iron Sets": ["irons", "ironset", "ironsets"],
    "Single Irons": [
        "iron", "single iron", "single irons",
        "1 iron", "1 irons",
        "2 iron", "2 irons",
        "3 iron", "3 irons",
        "4 iron", "4 irons",
        "5 iron", "5 irons",
        "6 iron", "6 irons",
        "7 iron", "7 irons",
        "8 iron", "8 irons",
        "9 iron", "9 irons",
    ],
    "Wedges": ["wedge", "wedges", "gw", "pw", "aw", "lw", "sw"],
    "Utility Irons": ["utility", "udi", "crossover"],
    "Putters": ["putter", "putters", "mallet", "putt", "scotty", "putting"],
}

def classify_query_is_model_specific(user_query: str, selected_club_type: str) -> dict:
    """Return dict with model-specific classification and club type mismatch detection.
    
    Returns:
        {
            "is_model_specific": bool,
            "potential_clubtype_mismatch": bool,
            "intended_club_type": str or None
        }
    """
    try:
        with open(os.path.join("textdocs", "brandlist.txt"), encoding="utf‑8") as f:
            brand_list = f.read().strip()
    except Exception as e:
        print("Error reading brandlist.txt:", e)
        brand_list = ""

    system_prompt = (
        "You are the first step in a natural-language golf-search tool. "
        "Reply with '1' if the query is model-specific or '0' if generic. "
        "Never output anything except '1' or '0'.\n\n"
        "EXAMPLES  respond ONLY with 1 or 0\n"
        'User: "ping irons"                   0\n'
        'User: "titleist drivers"             0\n'
        'User: "ping g430 driver"             1\n'
        'User: "taylormade spider putters"    1\n'
        'User: "mizuno jpx 923 forged"        1\n\n'
        "These names are BRANDS, not models  do *not* treat them as models:\n" + brand_list
    )

    # Debug: dump classification system prompt if enabled
    if DEBUG_DUMP_SYSTEM_PROMPT:
        print("\n" + "="*80)
        print("CLASSIFICATION SYSTEM PROMPT DEBUG DUMP")
        print("="*80)
        print(f"User Query: {user_query}")
        print(f"Selected Club Type: {selected_club_type}")
        print("-"*80)
        print(system_prompt)
        print("="*80 + "\n")

    try:
        resp = client.chat.completions.create(
            model=CLASSIFICATION_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_query},
            ],
            temperature=0,
            max_tokens=2,
        )
        result = resp.choices[0].message.content.lstrip()[:1]
        print(f"[DEBUG] classification result: {result}")
        is_model_specific = result == "1"
    except Exception as e:
        print("OpenAI classification error:", e)
        is_model_specific = False

    # Pure-Python club type mismatch detection using keyword map
    # NOTE: We explicitly ignore Utility Irons entirely in mismatch logic to avoid confusion.
    potential_clubtype_mismatch = False
    intended_club_type = None
    
    # Skip mismatch detection entirely if Utility Irons is selected
    if selected_club_type != "Utility Irons":
        query_lc = user_query.lower()
        selected_keywords = CLUB_TYPE_KEYWORDS.get(selected_club_type, [])
        mentioned_types = []
        for ctype, keywords in CLUB_TYPE_KEYWORDS.items():
            if ctype == "Utility Irons":
                continue  # do not use Utility Irons for mismatch detection
            for kw in keywords:
                if kw in query_lc:
                    mentioned_types.append(ctype)
                    break

        # If the query clearly mentions a different club type than selected
        for ctype in mentioned_types:
            if ctype != selected_club_type:
                potential_clubtype_mismatch = True
                intended_club_type = ctype
                break

    return {
        "is_model_specific": is_model_specific,
        "potential_clubtype_mismatch": potential_clubtype_mismatch,
        "intended_club_type": intended_club_type,
    }

def extract_and_map_models(user_query: str, club_type: str) -> str:
    """Return comma‑separated pairs userReference=OfficialName (≤7)."""
    try:
        model_file = MODEL_DATA_FILES.get(club_type, "drivers.txt")
        with open(os.path.join("model_data", model_file), "r") as f:
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
            model=EXTRACTION_MODEL,
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

def build_url_with_llm(user_query: str, system_prompt: str, mapped_models: str) -> str:
    """Build URL using LLM with deterministic model parameters."""
    # Build model filter chunk ourselves
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
            model=URL_BUILDING_MODEL,
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