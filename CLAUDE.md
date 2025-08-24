# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

This is a Flask application with Python dependencies managed via requirements.txt:

- `python -m venv venv` - Create virtual environment
- `source venv/bin/activate` (Linux/Mac) or `venv\Scripts\activate` (Windows) - Activate virtual environment
- `pip install -r requirements.txt` - Install dependencies
- `python app.py` - Run the development server (starts on port 5000)
- `gunicorn app:app` - Run in production mode using Gunicorn

## Architecture Overview

This is a natural language golf equipment search application that processes user queries and converts them into structured searches on 2ndswing.com. The application features a modular architecture with configurable prompt systems.

### Core Application Structure

- **app.py** - Main Flask application with global state management and dual architecture support
- **config.py** - Centralized configuration for club mappings, visible attributes, and Flask settings
- **services/llm_service.py** - OpenAI API integration for query processing and URL generation
- **services/scraper.py** - Web scraping functionality for 2ndswing.com product data extraction

### Dual Architecture System

The application supports two prompt architectures via the `use_new_architecture` toggle:

**V1 Architecture (prompts_v1/)**: 
- Model extraction for model-specific queries only
- Traditional parameter-based URL filtering

**V2 Architecture (prompts_v2/)**:
- Skips model extraction, uses q= parameter for search
- Includes query classification context in prompts

### Processing Pipeline

1. **Query Classification** (`classify_query_is_model_specific`) - GPT-4.1 determines if query references specific models vs generic brands
2. **Model Extraction** (`extract_and_map_models`) - Maps user-mentioned models to official names (V1 only)
3. **URL Generation** (`build_url_with_llm`) - Uses club-specific prompts to build 2ndswing.com filter URLs
4. **Data Scraping** (`scrape_2ndswing`) - Extracts product information with dynamic attribute capture

### Data Structure

- **model_data/** - Official model names for each club type (drivers.txt, fairways.txt, etc.)
- **textdocs/prompts_v1/** - Original prompt system files
- **textdocs/prompts_v2/** - New architecture prompt files  
- **textdocs/placeholder-text/** - Dynamic placeholder text for search interface
- **textdocs/brandlist.txt** - Golf brands list (distinguishes brands from models)

### Configuration

- **VISIBLE_ATTRS** (config.py:38-46) - Defines displayed product attributes per club type
- **CLUB_PROMPT_FILES** (config.py:16-24) - Maps club types to prompt files
- **MODEL_DATA_FILES** (config.py:27-35) - Maps club types to model data files
- **PLACEHOLDERS** - Dynamically loaded from placeholder-text/ directory
- Rate limiting: 350 requests/hour via flask-limiter
- OpenAI integration uses GPT-4.1 model with temperature=0 for deterministic results

### Frontend Architecture

Single-page application with inline HTML template featuring:
- Dynamic placeholder text rotation based on selected club type
- Architecture toggle switch for testing different prompt systems
- Spinner overlay during search processing  
- Keyboard shortcut (Enter) for form submission
- Staggered fade-in animations for search results
- Global state management with POST-redirect-GET pattern

### Environment Requirements

- **OPENAI_API_KEY** environment variable required for LLM functionality
- Python 3.x with virtual environment recommended
- Application scrapes 2ndswing.com using specific CSS selectors for product data extraction