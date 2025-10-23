# Architecture Migration - Catalog Search Only

## Summary
Successfully migrated the application to **exclusively use the new catalog search architecture** (prompts_v2). The toggle switch has been completely removed, and all searches now use the unified approach with `catalogsearch/result` for model-specific queries.

## Changes Made

### 1. Backend (`app.py`)
- **Removed** `use_new_architecture` variable and all related logic
- **Removed** conditional architecture selection - now always uses `prompts_v2`
- **Removed** old model extraction logic (`extract_and_map_models` is no longer called)
- **Simplified** the POST handler to always:
  1. Classify query as MODEL_SPECIFIC or GENERIC
  2. Load prompt from `prompts_v2` directory
  3. Prepend CLASSIFICATION and CLUB_TYPE to system prompt
  4. Build URL with LLM (passing empty string for mapped_models since we use `q=` parameter)
- **Removed** `use_new_architecture` from all `render_template()` calls
- **Removed** `use_new_architecture` from `/search_with_url` endpoint
- **Removed** unused import of `extract_and_map_models`

### 2. Frontend (`templates/index.html`)
- **Removed** architecture toggle UI (checkbox, labels, container)
- **Removed** all CSS for toggle switch and architecture toggle container
- **Removed** JavaScript event handler for toggle state changes
- **Removed** reference to `architecture_toggle` in filter removal JavaScript

### 3. How It Works Now
All searches follow this flow:
1. User enters query and selects club type
2. Query is classified as MODEL_SPECIFIC or GENERIC
3. System prompt from `prompts_v2/{club_type}.txt` is loaded
4. CLASSIFICATION and CLUB_TYPE are prepended to prompt
5. LLM generates URL following the rules:
   - **MODEL_SPECIFIC**: Uses `catalogsearch/result?g2_category={category}&q={model}&[filters]`
   - **GENERIC**: Uses dedicated listing pages like `golf-clubs/drivers?[filters]`
6. Results are scraped and displayed

## Testing Checklist
- [ ] Model-specific searches (e.g., "ping g430 driver") use catalogsearch endpoint
- [ ] Generic searches (e.g., "titleist drivers under $300") use dedicated listing pages
- [ ] All club types work correctly (Driver, Fairway Woods, Hybrids, Iron Sets, Wedges, Putters, Single Irons)
- [ ] Sorting parameters are applied correctly
- [ ] Filter removal works without errors
- [ ] No console errors related to missing toggle elements

## Notes
- The `extract_and_map_models` function still exists in `llm_service.py` but is no longer used
- All prompts in `prompts_v2` now include the Sorting section with 6 sort options
- The lint errors in `index.html` line 1191 are false positives from Flask/Jinja2 template syntax
