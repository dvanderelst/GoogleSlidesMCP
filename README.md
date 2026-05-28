# GoogleSlidesMCP

An MCP (Model Context Protocol) server that gives Claude access to your Google Slides presentations — text, speaker notes, and rendered slide images for inspecting equations and figures.

## Features

- List your presentations from Google Drive
- Read all text (titles, body, tables) and **speaker notes** from a deck
- Search inside a deck for matching slides
- Render any slide to PNG so Claude can visually inspect equations and figures that text extraction misses

## Requirements

- A Google account
- A Google Cloud project with the Slides API and Drive API enabled
- Python 3.10+ (recommended: [uv](https://docs.astral.sh/uv/) handles the venv and dependencies in one command)
- A Railway account (or any host that runs a Python web app)

## Setup

You only do the Google side once. Budget about 10 minutes.

### 1. Create / pick a Google Cloud project

1. Go to [console.cloud.google.com](https://console.cloud.google.com/).
2. Top-left dropdown next to "Google Cloud" → **New Project** (or reuse an existing personal one).
3. Name it something like `slides-mcp`. No organization needed. Click **Create**, then make sure the project dropdown shows it.

### 2. Enable the two APIs

1. Left menu → **APIs & Services → Library**.
2. Search **"Google Slides API"** → click it → **Enable**.
3. Back to Library, search **"Google Drive API"** → click it → **Enable**.

Drive is needed so `list_presentations` can find decks by name; Slides on its own can only fetch a presentation you already know the ID of.

### 3. Configure the OAuth consent screen (Google Auth Platform)

Google split the old "OAuth consent screen" page into a sidebar of tabs under **Google Auth Platform**. Use the left sidebar:

1. **Branding**
   - **App name:** `Slides MCP` (anything)
   - **User support email:** your email
   - **Developer contact email:** your email
   - Save.
2. **Audience**
   - **User type:** External (if not already set).
   - **Publishing status:** leave as **Testing**.
   - Under **Test users**, click **+ Add users** and add your own Google address. Save.
3. **Data access** — leave alone. The server requests scopes at runtime.

The app stays in **Testing** mode forever, which is fine for personal use. If a refresh token ever stops working, re-run `generate_token.py`.

### 4. Create the OAuth client

1. In the left sidebar, click **Clients**, then **+ Create client** at the top.
   - Shortcut: paste this URL with your project selected in the top bar — it lands directly on the Clients tab: <https://console.cloud.google.com/auth/clients>
   - Alternatively, top-left hamburger menu (≡) → **APIs & Services → Credentials → + Create credentials → OAuth client ID** works too.
2. Fill in the form:
   - **Application type:** `Desktop app` (this is critical — Web app will not work)
   - **Name:** `slides-mcp-desktop` (anything)
   - Click **Create**.
3. You're returned to the Clients list. Find the row for `slides-mcp-desktop` and click the **download icon** (a small downward arrow on the right side of the row). This downloads a JSON file with a name like `client_secret_…apps.googleusercontent.com.json`.
4. Rename that file to **`client_secret.json`** and move it into the repo folder next to `server.py`:

   ```
   /home/dieter/Dropbox/PythonRepos/GoogleSlidesMCP/client_secret.json
   ```

   It is already in `.gitignore`, so it won't be committed.

### 5. Generate a refresh token (one time, local)

This project is configured for [uv](https://docs.astral.sh/uv/). One command handles venv creation, dependency install, and execution:

```bash
uv run generate_token.py
```

If you don't have uv installed, the plain-Python fallback is:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python generate_token.py
```

A browser opens for consent → pick your Google account → expect a **"Google hasn't verified this app"** warning → **Advanced → Go to Slides MCP (unsafe)** → Allow.

The script prints all four values you need:

```
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
GOOGLE_REFRESH_TOKEN=...
MCP_AUTH_TOKEN=...
```

`MCP_AUTH_TOKEN` is a freshly generated 64-character hex string used to protect the SSE endpoint. Save it somewhere safe — you'll also append it to your Claude MCP URL as `?token=<MCP_AUTH_TOKEN>`. Re-running the script mints a new one, so update Railway and your Claude config together if you do.

### 6. Deploy to Railway

1. Push this repo to GitHub (remote already at https://github.com/dvanderelst/GoogleSlidesMCP):

   ```bash
   git push -u origin main
   ```
2. On [railway.com](https://railway.com): **New Project → Deploy from GitHub repo → GoogleSlidesMCP**.
3. In the Railway service's **Variables**, paste all four:
   - `GOOGLE_CLIENT_ID`
   - `GOOGLE_CLIENT_SECRET`
   - `GOOGLE_REFRESH_TOKEN`
   - `MCP_AUTH_TOKEN`
4. Railway detects the `Procfile` and deploys automatically. Note the generated public URL.

### Run locally (optional)

```bash
export GOOGLE_CLIENT_ID=...
export GOOGLE_CLIENT_SECRET=...
export GOOGLE_REFRESH_TOKEN=...
uv run server.py
```

Listens on port `8080` by default. Set `PORT` to override.

### Gotchas

- **`redirect_uri_mismatch`** when running `generate_token.py`: the OAuth client type is wrong. Must be **Desktop app**, not Web.
- **`No refresh token returned`**: Google only issues a refresh token on first consent. Revoke the app at https://myaccount.google.com/permissions and re-run.
- **Refresh token stops working**: re-run `generate_token.py` and update `GOOGLE_REFRESH_TOKEN` in Railway.

## Connect Claude

The easiest path is to add the connector **once** at claude.ai. Claude Code and Claude Desktop automatically sync custom connectors from your account, so a single setup makes the server available everywhere.

### claude.ai (web)

1. Go to claude.ai → **Settings → Connectors → Add custom connector**.
2. Name it (e.g. `GoogleSlidesMCP`).
3. URL:

   ```
   https://your-app.railway.app/sse?token=your-secret-token
   ```

   `token` must match `MCP_AUTH_TOKEN` in Railway.
4. After it connects, restart any open Claude Code or Claude Desktop session so it picks up the new connector. The tools will appear with names like `mcp__claude_ai_GoogleSlidesMCP__list_presentations`.

### Manual config (fallback)

If you don't want to use account sync, add the server to `~/.claude/claude_desktop_config.json` (or the equivalent MCP config):

```json
{
  "mcpServers": {
    "slides": {
      "url": "https://your-app.railway.app/sse?token=your-secret-token"
    }
  }
}
```

## Available Tools

| Tool | Description |
|------|-------------|
| `list_presentations` | List Slides files from Drive, optionally filtered by name |
| `get_presentation` | Structural overview: title, slide count, per-slide ids and titles |
| `get_presentation_text` | All text from every slide, with speaker notes by default |
| `get_slide_text` | Text from one slide (1-based index), with speaker notes by default |
| `search_in_presentation` | Find slides matching a query string |
| `render_slide_as_image` | Render a slide as PNG — use for equations, figures, layout review |

## What this is good for

- **Reviewing definitions, prose, bullet content** — text extraction handles all of this well.
- **Reading your speaker notes** — often where your actual reasoning lives. Notes give Claude the most to work with.
- **Checking equations** — if equations are typed as text or Unicode, they come through fine. If they're inserted as **images** (LaTeX add-ons, screenshots), use `render_slide_as_image` so Claude can see them.
- **Checking figures and diagrams** — only via `render_slide_as_image`.

## Scopes

The server requests **read-only** scopes:

- `https://www.googleapis.com/auth/presentations.readonly`
- `https://www.googleapis.com/auth/drive.readonly`

No tool in this server can modify your presentations or Drive.
