# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

This is a Flask application with Python dependencies managed via requirements.txt:

- `pip install -r requirements.txt` - Install dependencies
- `python app.py` - Run the development server (starts on port 5000)
- `gunicorn app:app` - Run in production mode using Gunicorn

## Architecture Overview

This is a natural language golf equipment search application that processes user queries and converts them into structured searches on 2ndswing.com. The application uses a 4-step pipeline:

### Core Pipeline (app.py:62-254)

1. **Query Classification** (`classify_query_is_model_specific`) - Uses GPT-4.1 to determine if the query references specific golf club models vs generic brands
2. **Model Extraction** (`extract_and_map_models`) - Maps user-mentioned models to official model names from model_data/ files
3. **URL Generation** (`build_url_with_llm`) - Uses club-specific prompts to build 2ndswing.com filter URLs
4. **Data Scraping** (`scrape_2ndswing`) - Extracts product information from the generated URL

### Data Structure

- **model_data/** - Contains official model names for each club type (drivers.txt, fairways.txt, etc.)
- **textdocs/prompts/** - Club-specific system prompts for URL generation
- **textdocs/placeholder-text/** - Dynamic placeholder text for the search interface
- **textdocs/brandlist.txt** - List of golf brands (used to distinguish brands from models)

### Configuration

- **VISIBLE_ATTRS** (app.py:38-46) - Defines which product attributes to display for each club type
- **club_prompt_files** (app.py:27-35) - Maps club types to their corresponding prompt files
- OpenAI API integration uses GPT-4.1 model
- Rate limiting enabled via flask-limiter (350 requests/hour)

### Frontend

The application uses an inline HTML template with JavaScript for:
- Dynamic placeholder text rotation based on selected club type
- Spinner overlay during search processing
- Keyboard shortcut (Enter) for form submission
- Staggered fade-in animations for search results

### Environment Requirements

- **OPENAI_API_KEY** environment variable required for LLM functionality
- Application expects to scrape 2ndswing.com with specific CSS selectors for product data extraction