import uuid
from datetime import datetime, timezone
from pathlib import Path
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from .config import settings
from . import db
from .schemas import ProjectCreate
from .providers import integrations, storyboard, imagen, tts, render, mirror
from .youtube import router as youtube_router, upload as youtube_upload

app = FastAPI(title="AI Video Studio API", version="0.1.0",
              description="AI storyboard, image, narration, rendering and YouTube publishing API")
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_list, allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])
Path(settings.media_dir).mkdir(parents=True, exist_ok=True)
Path(settings.render_dir).mkdir(parents=True, exist_ok=True)
app.mount("/media", StaticFiles(directory=settings.media_dir), name="media")
app.mount("/renders", StaticFiles(directory=settings.render_dir), name="renders")
app.include_router(youtube_router, prefix="/api")

@app.on_event("startup")
def startup():
    db.init_db()

def get_project(project_id):
    with db.connection() as conn:
        row = conn.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Project not found.")
    return db.encode(row)

@app.get("/api/health")
def health():
    return {"status": "ok", "environment": settings.app_env, "integrations": integrations()}

@app.get("/api/projects")
def list_projects():
    with db.connection() as conn:
        rows = conn.execute("SELECT * FROM projects ORDER BY created_at DESC LIMIT 100").fetchall()
    return [db.encode(row) for row in rows]

@app.post("/api/projects", status_code=201)
def create_project(payload: ProjectCreate):
    now = datetime.now(timezone.utc).isoformat()
    project_id = str(uuid.uuid4())
    with db.connection() as conn:
        conn.execute("INSERT INTO projects(id,title,topic,style,format,duration_minutes,status,scenes_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (project_id, payload.topic[:100], payload.topic, payload.style, payload.format,
             payload.duration_minutes, "draft", "[]", now, now))
    project = get_project(project_id)
    mirror(project)
    return project

async def generation_task(project_id):
    try:
        project = get_project(project_id)
        scenes = await storyboard(project["topic"], project["style"], project["format"], project["duration_minutes"])
        folder = Path(settings.media_dir) / project_id
        folder.mkdir(parents=True, exist_ok=True)
        for scene in scenes:
            image_path = folder / f"scene-{scene['id']}.png"
            audio_path = folder / f"scene-{scene['id']}.mp3"
            if await imagen(scene["visual_prompt"], image_path):
                scene["image_path"] = str(image_path)
            if await tts(scene["narration"], audio_path):
                scene["audio_path"] = str(audio_path)
        db.update(project_id, status="script_ready", scenes_json=scenes, error=None)
        mirror(get_project(project_id))
    except Exception as exc:
        db.update(project_id, status="failed", error=str(exc)[:500])
        mirror(get_project(project_id))

@app.post("/api/projects/{project_id}/generate")
def generate_project(project_id: str, background_tasks: BackgroundTasks):
    project = get_project(project_id)
    if project["status"] in {"generating", "rendering"}:
        raise HTTPException(409, "Project is already processing.")
    if not settings.gemini_api_key:
        raise HTTPException(503, "Gemini is not configured. Add GEMINI_API_KEY to generate a real script.")
    db.update(project_id, status="generating", error=None)
    background_tasks.add_task(generation_task, project_id)
    return get_project(project_id)

def render_task(project_id):
    try:
        project = get_project(project_id)
        url = render(project_id, project["scenes"], project["format"])
        db.update(project_id, status="completed", render_url=url, error=None)
        mirror(get_project(project_id))
    except Exception as exc:
        db.update(project_id, status="failed", error=("Render failed: " + str(exc))[:500])
        mirror(get_project(project_id))

@app.post("/api/projects/{project_id}/render")
def render_project(project_id: str, background_tasks: BackgroundTasks):
    project = get_project(project_id)
    if not project["scenes"]:
        raise HTTPException(409, "Generate a storyboard before rendering.")
    if project["status"] == "rendering":
        raise HTTPException(409, "Project is already rendering.")
    db.update(project_id, status="rendering", error=None)
    background_tasks.add_task(render_task, project_id)
    return get_project(project_id)

@app.post("/api/projects/{project_id}/publish")
def publish_project(project_id: str, privacy_status: str = "private", description: str = ""):
    project = get_project(project_id)
    if not project.get("render_url"):
        raise HTTPException(409, "Render the project before uploading it.")
    if privacy_status not in {"private", "unlisted", "public"}:
        raise HTTPException(400, "Invalid privacy status.")
    path = (Path(settings.render_dir) / Path(project["render_url"]).name).resolve()
    return youtube_upload(str(path), project["title"], description, privacy_status)

@app.get("/api/projects/{project_id}")
def project(project_id: str):
    return get_project(project_id)

@app.get("/api/projects/{project_id}/download")
def download(project_id: str):
    project = get_project(project_id)
    if not project["render_url"]:
        raise HTTPException(409, "Project has not been rendered.")
    return {"url": project["render_url"]}

@app.get("/api/integrations")
def integration_status():
    return integrations()
