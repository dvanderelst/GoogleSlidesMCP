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
- Python 3.10+
- A Railway account (or any host that runs a Python web app)

## Setup

### 1. Create Google OAuth credentials

1. Go to [console.cloud.google.com](https://console.cloud.google.com/), create (or reuse) a project.
2. Enable two APIs: **Google Slides API** and **Google Drive API**.
3. Configure the **OAuth consent screen** (External, just yourself as a test user is fine).
4. Under **Credentials → Create credentials → OAuth client ID**, choose application type **Desktop app**. Download the JSON.
5. Save that file next to `server.py` as `client_secret.json` (it is gitignored).

### 2. Generate a refresh token (one time, local)

```bash
pip install -r requirements.txt
python generate_token.py
```

A browser opens for consent. On success the script prints three values:

```
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
GOOGLE_REFRESH_TOKEN=...
```

Keep these — you'll paste them into Railway.

### 3. Deploy to Railway

1. Push this repo to GitHub (already done at https://github.com/dvanderelst/GoogleSlidesMCP).
2. Create a new project on [railway.com](https://railway.com) from the repo.
3. Add these environment variables in Railway's dashboard:
   - `GOOGLE_CLIENT_ID`
   - `GOOGLE_CLIENT_SECRET`
   - `GOOGLE_REFRESH_TOKEN`
   - `MCP_AUTH_TOKEN` — a secret string you choose; required to protect the SSE endpoint
4. Railway detects the `Procfile` and deploys automatically.

### 4. Run locally (optional)

```bash
export GOOGLE_CLIENT_ID=...
export GOOGLE_CLIENT_SECRET=...
export GOOGLE_REFRESH_TOKEN=...
python server.py
```

Listens on port `8080` by default. Set `PORT` to override.

## Connect Claude

### claude.ai (web)

Settings → Integrations → Add custom integration. URL:

```
https://your-app.railway.app/sse?token=your-secret-token
```

(`token` must match `MCP_AUTH_TOKEN` in Railway.)

### Claude Desktop / Claude Code

Add to `~/.claude/claude_desktop_config.json` (or the equivalent MCP config):

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
