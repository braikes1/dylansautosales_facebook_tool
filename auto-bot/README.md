# Auto Bot

Chrome side-panel extension + local FastAPI API to scrape vehicle listings
and help fill Facebook Marketplace vehicle listings.

## Layout

- `extension/` — load this as an unpacked extension in Chrome.
- `api/` — Python FastAPI server that uses OpenAI to extract vehicle data
  and pick vehicle photos.

## Running the API

1. Create and activate a virtualenv (recommended), then install deps:

   ```bash
   cd api
   pip install -r requirements.txt
   ```

2. Set your OpenAI API key in the environment:

   ```bash
   export OPENAI_API_KEY="sk-..."
   ```

   On Windows PowerShell:

   ```powershell
   setx OPENAI_API_KEY "sk-..."
   ```

3. Start the server:

   ```bash
   uvicorn main:app --reload
   ```

   By default it listens on `http://127.0.0.1:8000`.

## Using the extension

1. In Chrome, go to `chrome://extensions`, enable **Developer mode**.
2. Click **Load unpacked** and select the `extension` folder.
3. Open a dealership inventory page, then open the Auto Bot side panel
   (via the puzzle icon → Auto Bot → Open side panel).
4. Click **Scrape this page** to see detected vehicle tiles.
5. Click a tile to open the **Details** tab. The extension will call the
   API to fetch AI-enriched vehicle data and candidate photos.
6. Edit the description as needed, then click **Send to Facebook**.
   A Facebook Marketplace vehicle create page will open; a "Fill from Auto Bot"
   button will appear. Once clicked, it will attempt to fill in title, price,
   mileage, and description fields.

> Note: DOM structure on dealership sites and Facebook can change. You may
> need to tweak selectors in `panel.js` (scraper) and `fb_fill.js`
> (form filler) to perfectly match your environment.
