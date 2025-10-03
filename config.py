import os
import glob
import json

# Flask Configuration
FLASK_PORT = 5000
FLASK_DEBUG = True

# Rate Limiting
RATE_LIMIT = "350 per hour"

# OpenAI Configuration
OPENAI_MODEL = "gpt-4.1"

# Debug Configuration
DEBUG_DUMP_SYSTEM_PROMPT = True  # Set to False to disable system prompt logging

# Club type to prompt file mapping
CLUB_PROMPT_FILES = {
    "Driver": "driver.txt",
    "Fairway Woods": "fairway.txt",
    "Hybrids": "hybrid.txt",
    "Iron Sets": "ironset.txt",
    "Wedges": "wedge.txt",
    "Putters": "putter.txt",
    "Single Irons": "singleiron.txt",
}

# Model data file mapping
MODEL_DATA_FILES = {
    "Driver": "drivers.txt",
    "Fairway Woods": "fairways.txt",
    "Hybrids": "hybrids.txt",
    "Iron Sets": "ironsets.txt",
    "Wedges": "wedges.txt",
    "Putters": "putters.txt",
    "Single Irons": "singleirons.txt",
}

# Visible attributes for each club type
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
    """Load placeholder texts from files."""
    bank = {}
    for path in glob.glob("textdocs/placeholder-text/*.txt"):
        key = os.path.splitext(os.path.basename(path))[0]   # driver, fairway…
        with open(path, encoding="utf-8") as f:
            bank[key] = [ln.strip() for ln in f if ln.strip()]
    return bank

# Load placeholders at module level
PLACEHOLDERS = load_placeholders() 