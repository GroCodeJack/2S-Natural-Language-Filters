# Mixpanel Instrumentation Guide

This document explains where Mixpanel is used in this codebase, what each piece does, how to configure it, and how to verify/troubleshoot.

## Overview
- **Backend events**: Sent from `app.py` using the Python Mixpanel SDK.
- **Frontend session replay**: Initialized in `templates/index.html` using the Mixpanel JS SDK.
- **Config**: Mixpanel Project Token is provided via environment variable `MIXPANEL_TOKEN`.

---

## Backend: Events in `app.py`
File: `app.py`

- **Where token comes from**
  - `os.environ.get("MIXPANEL_TOKEN")`
  - Passed into `render_template(..., mixpanel_token=...)` for frontend use.

- **Initialization per request (server-side)**
  - Each area that sends an event instantiates a Mixpanel client if the token is present:
    ```python
    if os.environ.get("MIXPANEL_TOKEN"):
        mp = mixpanel.Mixpanel(os.environ.get("MIXPANEL_TOKEN"))
    ```

- **Events sent**
  - Page View (on every request)
    ```python
    mp.track(request.remote_addr, 'Page View', {
        'page': 'home',
        'method': request.method,
        'user_agent': request.headers.get('User-Agent', ''),
        'referrer': request.headers.get('Referer', '')
    })
    ```
  - Search Performed (on POST to `/`)
    ```python
    mp.track(request.remote_addr, 'Search Performed', {
        'club_type': club_type,
        'user_query': user_query,
        'generated_url': generated_url,
        'applied_filters': applied_filters,
        'product_count': total_count or 0
    })
    ```
  - Search Performed (filter removal flow via `/search_with_url`)
    ```python
    mp.track(request.remote_addr, 'Search Performed', {
        'club_type': club_type,
        'user_query': user_query + " (filter removed)",
        'generated_url': url,
        'applied_filters': applied_filters,
        'product_count': total_count or 0
    })
    ```

Notes:
- Server events can be stitched to Session Replay using Distinct ID and time (Mixpanel Server-side Stitching). Consider calling `identify()` from the frontend if you have user IDs.

---

## Frontend: Session Replay in `templates/index.html`
File: `templates/index.html`

- **Where**: At the end of the document, just before `</body>`.
- **What**: Official Mixpanel JS stub + `mixpanel.init(...)` with Session Replay options.
- **Key snippet**:
  ```html
  <script>
    (function(f,b){ /* Official Mixpanel stub ... */ })(document,window.mixpanel||[]);
  </script>
  <script>
    (function(){
      var token = "{{ mixpanel_token or '' }}"; // injected from Flask
      if (!token) return;
      mixpanel.init(token, {
        record_sessions_percent: 100,
        record_mask_text_selector: '' // unmask on-screen text; inputs remain masked by design
        // record_heatmap_data: true,  // optional: enable heatmap clicks
      });

      // Debug helpers in Console
      window.getMixpanelReplayProps = function(){
        try { return mixpanel.get_session_recording_properties(); } catch (e) { return {}; }
      };
      window.getMixpanelReplayUrl = function(){
        try { return mixpanel.get_session_replay_url && mixpanel.get_session_replay_url(); } catch (e) { return null; }
      };
    })();
  </script>
  ```

- **Defaults and masking**
  - Mixpanel masks all input fields by default (cannot be disabled).
  - We unmask on-page text with `record_mask_text_selector: ''` so replay shows readable text content.

- **Sampling**
  - `record_sessions_percent: 100` captures all sessions. Reduce later (e.g., `10` or `1`).

- **Heatmaps (optional)**
  - Enable with `record_heatmap_data: true` to collect click data during recorded sessions.

---

## Configuration
- **Environment variable**
  - `MIXPANEL_TOKEN` must be set.
  - Local (macOS/zsh):
    ```bash
    export MIXPANEL_TOKEN=YOUR_PROJECT_TOKEN
    python app.py
    ```
  - Render.com:
    - Service → Environment → add `MIXPANEL_TOKEN=YOUR_PROJECT_TOKEN`, then redeploy.

---

## Verification
- **Frontend (Console)**
  - `window.getMixpanelReplayProps()` → returns `{ $mp_replay_id: ... }` during active recording.
  - `window.getMixpanelReplayUrl()` → returns a Mixpanel URL while recording.
  - `window.mixpanel && typeof mixpanel.init === 'function'` → should be `true`.

- **Mixpanel UI**
  - Session Replay → confirm new replays appear.
  - Events → verify `Page View` and `Search Performed` contain expected props.

---

## Privacy & Masking
- **Inputs**: Always masked by Mixpanel for privacy.
- **On-page text**: Unmasked via `record_mask_text_selector: ''`.
- **Further controls**:
  - `record_block_selector`: Block entire elements (default blocks `img, video`). Set to `''` to un-block.
  - `record_mask_text_class`: Provide a class (or regex) to selectively re-mask specific areas.

---

## Troubleshooting
- **Error: "mixpanel object not initialized"**
  - Ensure the stub snippet is present and the CDN loads.
  - Verify token is injected (not empty) and `mixpanel.init` is called after the stub.
- **All text starred out**
  - Ensure `record_mask_text_selector: ''` is set.
  - Inputs remain masked by design (expected behavior).
- **No replays showing**
  - Check sampling (`record_sessions_percent`) and network blockers (ad blockers may block `cdn.mxpnl.com`).
  - Consider a fallback CDN if necessary.

---

## File Map
- **`app.py`**
  - Emits Mixpanel events (`Page View`, `Search Performed`).
  - Reads `MIXPANEL_TOKEN` from environment; passes `mixpanel_token` to template.
- **`templates/index.html`**
  - Loads Mixpanel JS stub and initializes Session Replay.
  - Sets masking and sampling settings; exposes debug helpers.

---

## Future Enhancements
- Add `identify()` calls on the frontend when a user ID is available to improve Server-side Stitching.
- Toggle sampling per environment (e.g., 100% in staging, lower in production).
- Add selective re-masking classes for any sensitive UI regions if needed.
