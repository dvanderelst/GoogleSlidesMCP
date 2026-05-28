import base64
import os
from typing import Any

import httpx
import uvicorn
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.utilities.types import Image
from mcp.server.sse import SseServerTransport
from starlette.applications import Starlette
from starlette.routing import Mount, Route

GOOGLE_CLIENT_ID = os.environ["GOOGLE_CLIENT_ID"]
GOOGLE_CLIENT_SECRET = os.environ["GOOGLE_CLIENT_SECRET"]
GOOGLE_REFRESH_TOKEN = os.environ["GOOGLE_REFRESH_TOKEN"]

SCOPES = [
    "https://www.googleapis.com/auth/presentations.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]

mcp = FastMCP("GoogleSlidesMCP")


def get_credentials() -> Credentials:
    return Credentials(
        token=None,
        refresh_token=GOOGLE_REFRESH_TOKEN,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=GOOGLE_CLIENT_ID,
        client_secret=GOOGLE_CLIENT_SECRET,
        scopes=SCOPES,
    )


def slides_service():
    return build("slides", "v1", credentials=get_credentials(), cache_discovery=False)


def drive_service():
    return build("drive", "v3", credentials=get_credentials(), cache_discovery=False)


# ---------- text extraction helpers ----------

def _text_from_text_element(elements: list[dict]) -> str:
    parts = []
    for el in elements:
        run = el.get("textRun")
        if run and run.get("content"):
            parts.append(run["content"])
    return "".join(parts)


def _text_from_shape(shape: dict) -> str:
    text = shape.get("text")
    if not text:
        return ""
    return _text_from_text_element(text.get("textElements", []))


def _text_from_table(table: dict) -> str:
    rows = []
    for row in table.get("tableRows", []):
        cells = []
        for cell in row.get("tableCells", []):
            cell_text = _text_from_text_element(
                cell.get("text", {}).get("textElements", [])
            )
            cells.append(cell_text.strip())
        rows.append(" | ".join(cells))
    return "\n".join(rows)


def _text_from_page_elements(page_elements: list[dict]) -> list[str]:
    out = []
    for pe in page_elements:
        if "shape" in pe:
            t = _text_from_shape(pe["shape"])
            if t.strip():
                out.append(t.rstrip())
        elif "table" in pe:
            t = _text_from_table(pe["table"])
            if t.strip():
                out.append(t)
        elif "elementGroup" in pe:
            out.extend(_text_from_page_elements(pe["elementGroup"].get("children", [])))
        elif "image" in pe:
            out.append("[image]")
    return out


def _notes_text(slide: dict) -> str:
    notes_page = slide.get("slideProperties", {}).get("notesPage")
    if not notes_page:
        return ""
    chunks = _text_from_page_elements(notes_page.get("pageElements", []))
    return "\n".join(c for c in chunks if c.strip() and c != "[image]")


def _slide_title(slide: dict) -> str:
    """Best-effort title: first non-empty text in the slide."""
    for pe in slide.get("pageElements", []):
        if "shape" in pe:
            t = _text_from_shape(pe["shape"]).strip()
            if t:
                return t.splitlines()[0]
    return "(no title)"


def _format_slide(index: int, slide: dict, include_notes: bool = True) -> str:
    slide_id = slide.get("objectId", "")
    title = _slide_title(slide)
    body_chunks = _text_from_page_elements(slide.get("pageElements", []))
    body = "\n".join(body_chunks).strip()

    parts = [f"Slide {index + 1} (id={slide_id}) — {title}", "", body or "(empty)"]

    if include_notes:
        notes = _notes_text(slide)
        if notes.strip():
            parts.extend(["", "Speaker notes:", notes.strip()])

    return "\n".join(parts)


# ---------- MCP tools ----------

@mcp.tool()
def list_presentations(query: str = "", limit: int = 20) -> str:
    """List Google Slides presentations in Drive. Optional query matches filenames (case-insensitive substring)."""
    drive = drive_service()
    q = "mimeType='application/vnd.google-apps.presentation' and trashed=false"
    if query:
        safe = query.replace("'", "\\'")
        q += f" and name contains '{safe}'"

    resp = drive.files().list(
        q=q,
        pageSize=min(limit, 100),
        fields="files(id, name, modifiedTime, webViewLink)",
        orderBy="modifiedTime desc",
    ).execute()

    files = resp.get("files", [])
    if not files:
        return "No presentations found."

    lines = [
        f"ID: {f['id']} | {f['name']} | modified: {f.get('modifiedTime', '?')}"
        for f in files
    ]
    return f"{len(files)} presentation(s):\n\n" + "\n".join(lines)


@mcp.tool()
def get_presentation(presentation_id: str) -> str:
    """Get structural overview of a presentation: title, slide count, and per-slide ids + titles. Use this first to orient yourself."""
    svc = slides_service()
    pres = svc.presentations().get(presentationId=presentation_id).execute()

    slides = pres.get("slides", [])
    lines = [
        f"Title: {pres.get('title', '(untitled)')}",
        f"Presentation ID: {pres.get('presentationId', presentation_id)}",
        f"Slide count: {len(slides)}",
        "",
        "Slides:",
    ]
    for i, slide in enumerate(slides):
        lines.append(f"  {i + 1}. id={slide.get('objectId', '')} — {_slide_title(slide)}")

    return "\n".join(lines)


@mcp.tool()
def get_presentation_text(presentation_id: str, include_notes: bool = True) -> str:
    """Return all text from every slide in the presentation, including speaker notes by default."""
    svc = slides_service()
    pres = svc.presentations().get(presentationId=presentation_id).execute()
    slides = pres.get("slides", [])

    if not slides:
        return "Presentation has no slides."

    blocks = [_format_slide(i, s, include_notes=include_notes) for i, s in enumerate(slides)]
    return "\n\n---\n\n".join(blocks)


@mcp.tool()
def get_slide_text(presentation_id: str, slide_index: int, include_notes: bool = True) -> str:
    """Return text (and optionally speaker notes) for a single slide. slide_index is 1-based."""
    svc = slides_service()
    pres = svc.presentations().get(presentationId=presentation_id).execute()
    slides = pres.get("slides", [])

    if slide_index < 1 or slide_index > len(slides):
        return f"slide_index out of range (1..{len(slides)})."

    return _format_slide(slide_index - 1, slides[slide_index - 1], include_notes=include_notes)


@mcp.tool()
def search_in_presentation(presentation_id: str, query: str, include_notes: bool = True) -> str:
    """Find slides whose text (or speaker notes) contains the query (case-insensitive). Returns matching slide indices and a snippet."""
    svc = slides_service()
    pres = svc.presentations().get(presentationId=presentation_id).execute()
    slides = pres.get("slides", [])

    needle = query.lower()
    hits = []
    for i, slide in enumerate(slides):
        body = "\n".join(_text_from_page_elements(slide.get("pageElements", [])))
        notes = _notes_text(slide) if include_notes else ""
        haystack = (body + "\n" + notes).lower()
        if needle in haystack:
            title = _slide_title(slide)
            hits.append(f"Slide {i + 1} — {title}")

    if not hits:
        return f"No matches for: {query}"

    return f"{len(hits)} match(es):\n\n" + "\n".join(hits)


@mcp.tool()
def render_slide_as_image(presentation_id: str, slide_index: int) -> Image:
    """Render a slide as a PNG image. Use this to inspect equations, figures, or layout that text extraction misses. slide_index is 1-based."""
    svc = slides_service()
    pres = svc.presentations().get(presentationId=presentation_id).execute()
    slides = pres.get("slides", [])

    if slide_index < 1 or slide_index > len(slides):
        raise ValueError(f"slide_index out of range (1..{len(slides)})")

    slide_object_id = slides[slide_index - 1]["objectId"]

    thumb = svc.presentations().pages().getThumbnail(
        presentationId=presentation_id,
        pageObjectId=slide_object_id,
        thumbnailProperties_mimeType="PNG",
        thumbnailProperties_thumbnailSize="LARGE",
    ).execute()

    content_url = thumb.get("contentUrl")
    if not content_url:
        raise RuntimeError("Slides API returned no contentUrl for thumbnail.")

    with httpx.Client(timeout=30.0) as client:
        resp = client.get(content_url)
        resp.raise_for_status()
        png_bytes = resp.content

    return Image(data=png_bytes, format="png")


# ---------- SSE transport (mirrors ZoteroMCP) ----------

sse_transport = SseServerTransport("/messages/")

MCP_AUTH_TOKEN = os.environ.get("MCP_AUTH_TOKEN", "")


def is_authorized(request) -> bool:
    if not MCP_AUTH_TOKEN:
        return True
    token = request.query_params.get("token", "")
    return token == MCP_AUTH_TOKEN


async def handle_sse(request):
    from starlette.responses import Response
    if not is_authorized(request):
        return Response("Unauthorized", status_code=401)
    async with sse_transport.connect_sse(
        request.scope, request.receive, request._send
    ) as streams:
        await mcp._mcp_server.run(
            streams[0], streams[1],
            mcp._mcp_server.create_initialization_options(),
        )


app = Starlette(routes=[
    Route("/sse", endpoint=handle_sse),
    Mount("/messages/", app=sse_transport.handle_post_message),
])


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
