import os
from urllib.parse import quote_plus
from openai import OpenAI
from config import OPENAI_MODEL, MODEL_DATA_FILES

# Initialize OpenAI client
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

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
            model=OPENAI_MODEL,
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
            model=OPENAI_MODEL,
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
            model=OPENAI_MODEL,
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