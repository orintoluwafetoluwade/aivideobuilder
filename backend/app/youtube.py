import json
import secrets
import time
from pathlib import Path
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import RedirectResponse
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from .config import settings

router = APIRouter(prefix="/youtube", tags=["youtube"])
SCOPES = ["https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube.readonly"]
_states = {}

def make_flow(state=None):
    if not (settings.youtube_client_id and settings.youtube_client_secret):
        raise HTTPException(503, "Configure YouTube OAuth client credentials first.")
    config = {"web": {"client_id": settings.youtube_client_id, "client_secret": settings.youtube_client_secret,
        "redirect_uris": [settings.youtube_redirect_uri], "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token"}}
    return Flow.from_client_config(config, scopes=SCOPES, redirect_uri=settings.youtube_redirect_uri, state=state)

@router.get("/auth-url")
def auth_url():
    flow = make_flow()
    state = secrets.token_urlsafe(32)
    _states[state] = time.time()
    url, _ = flow.authorization_url(access_type="offline", include_granted_scopes="true", prompt="consent", state=state)
    return {"authorization_url": url}

@router.get("/callback")
def callback(code: str = Query(...), state: str = Query(...)):
    created = _states.pop(state, None)
    if created is None or time.time() - created > 600:
        raise HTTPException(400, "OAuth state is invalid or expired.")
    flow = make_flow(state)
    flow.fetch_token(code=code)
    if not settings.youtube_token_encryption_key:
        raise HTTPException(503, "Set YOUTUBE_TOKEN_ENCRYPTION_KEY before storing OAuth credentials.")
    try:
        from cryptography.fernet import Fernet
        token = Fernet(settings.youtube_token_encryption_key.encode()).encrypt(flow.credentials.to_json().encode()).decode()
        settings.youtube_token_path.parent.mkdir(parents=True, exist_ok=True)
        settings.youtube_token_path.write_text(token, encoding="utf-8")
        return RedirectResponse(settings.frontend_url + "/?youtube=connected")
    except Exception as exc:
        raise HTTPException(500, "Secure token storage failed. Check the Fernet encryption key.") from exc

@router.post("/upload")
def upload(file_path: str, title: str, description: str = "", privacy_status: str = "private"):
    if privacy_status not in {"private", "unlisted", "public"}:
        raise HTTPException(400, "Invalid privacy status.")
    if privacy_status == "public":
        raise HTTPException(400, "Public publishing is disabled until an explicit confirmation flow is implemented.")
    token = settings.youtube_token_path
    if not token.exists() or not settings.youtube_token_encryption_key:
        raise HTTPException(409, "Connect a YouTube channel first.")
    try:
        from cryptography.fernet import Fernet
        from google.oauth2.credentials import Credentials
        credentials = Credentials.from_authorized_user_info(
            json.loads(Fernet(settings.youtube_token_encryption_key.encode()).decrypt(token.read_bytes())), SCOPES)
        path = Path(file_path).resolve()
        render_root = Path(settings.render_dir).resolve()
        if path.parent != render_root or path.suffix.lower() != ".mp4":
            raise HTTPException(400, "Uploads must reference an MP4 in the configured render directory.")
        if not path.is_file():
            raise HTTPException(404, "Rendered video file not found.")
        service = build("youtube", "v3", credentials=credentials)
        media = MediaFileUpload(str(path), chunksize=8 * 1024 * 1024, resumable=True, mimetype="video/mp4")
        request = service.videos().insert(part="snippet,status",
            body={"snippet": {"title": title[:100], "description": description[:5000]},
                  "status": {"privacyStatus": privacy_status}}, media_body=media)
        response = None
        while response is None:
            _, response = request.next_chunk()
        return {"status": "uploaded", "video_id": response["id"], "url": "https://youtube.com/watch?v=" + response["id"]}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(502, "YouTube upload failed; verify OAuth scopes, quota, and credentials.") from exc
