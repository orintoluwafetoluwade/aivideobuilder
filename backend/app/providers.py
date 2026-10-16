import base64
import json
import subprocess
from pathlib import Path
import httpx
from .config import settings

def integrations():
    return {
        "gemini": bool(settings.gemini_api_key),
        "imagen": bool(settings.google_cloud_project and settings.google_application_credentials),
        "text_to_speech": bool(settings.google_tts_api_key or settings.google_application_credentials),
        "youtube": bool(settings.youtube_client_id and settings.youtube_client_secret),
        "firestore": bool(settings.firebase_project_id and settings.firebase_service_account_json),
    }

async def storyboard(topic, style, fmt, minutes):
    if not settings.gemini_api_key:
        raise RuntimeError("Gemini is not configured. Set GEMINI_API_KEY.")
    aspect = "vertical 9:16" if fmt == "YouTube Shorts" else "landscape 16:9"
    prompt = f"""Create a production-ready storyboard for a {minutes}-minute {aspect} YouTube video.
Topic: {topic}
Style: {style}
Return ONLY JSON with a scenes array. Each scene has title, narration (spoken words), visual_prompt (detailed image prompt with consistent visual continuity), and duration in seconds. Create 4-12 scenes totalling close to {minutes * 60} seconds. Do not include text in images."""
    async with httpx.AsyncClient(timeout=90) as client:
        response = await client.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{settings.gemini_model}:generateContent",
            params={"key": settings.gemini_api_key},
            json={"contents": [{"parts": [{"text": prompt}]}],
                  "generationConfig": {"responseMimeType": "application/json", "temperature": 0.7}},
        )
        response.raise_for_status()
        raw = response.json()["candidates"][0]["content"]["parts"][0]["text"]
    data = json.loads(raw)
    items = data.get("scenes", data if isinstance(data, list) else [])
    if not isinstance(items, list) or not items:
        raise RuntimeError("Gemini returned no usable scenes.")
    return [{
        "id": i, "title": str(item.get("title", f"Scene {i}"))[:140],
        "narration": str(item.get("narration", ""))[:4500],
        "visual_prompt": str(item.get("visual_prompt", topic))[:2000],
        "duration": max(2, min(120, float(item.get("duration", 8)))),
        "image_path": None, "audio_path": None,
    } for i, item in enumerate(items[:12], 1)]

async def imagen(prompt, path):
    if not settings.google_cloud_project:
        return False
    try:
        from google.auth import default
        from google.auth.transport.requests import Request
        credentials, _ = default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        credentials.refresh(Request())
        url = (f"https://{settings.google_cloud_location}-aiplatform.googleapis.com/v1/projects/"
               f"{settings.google_cloud_project}/locations/{settings.google_cloud_location}/publishers/google/"
               f"models/{settings.vertex_imagen_model}:predict")
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(url, headers={"Authorization": f"Bearer {credentials.token}"},
                json={"instances": [{"prompt": prompt}], "parameters": {"sampleCount": 1, "aspectRatio": "16:9"}})
            response.raise_for_status()
            prediction = response.json()["predictions"][0]
        encoded = prediction.get("bytesBase64Encoded") or prediction.get("image", {}).get("bytesBase64Encoded")
        if not encoded:
            return False
        path.write_bytes(base64.b64decode(encoded))
        return True
    except Exception:
        return False

async def tts(text, path):
    if not text.strip():
        return False
    try:
        if settings.google_tts_api_key:
            async with httpx.AsyncClient(timeout=90) as client:
                response = await client.post("https://texttospeech.googleapis.com/v1/text:synthesize",
                    params={"key": settings.google_tts_api_key},
                    json={"input": {"text": text[:4500]},
                          "voice": {"languageCode": "en-US", "name": settings.google_tts_voice},
                          "audioConfig": {"audioEncoding": "MP3"}})
                response.raise_for_status()
                path.write_bytes(base64.b64decode(response.json()["audioContent"]))
        else:
            from google.cloud import texttospeech
            client = texttospeech.TextToSpeechClient()
            response = client.synthesize_speech(
                input=texttospeech.SynthesisInput(text=text[:4500]),
                voice=texttospeech.VoiceSelectionParams(language_code="en-US", name=settings.google_tts_voice),
                audio_config=texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.MP3))
            path.write_bytes(response.audio_content)
        return True
    except Exception:
        return False

def render(project_id, scenes, fmt):
    ffmpeg = "ffmpeg"
    folder = Path(settings.media_dir).resolve() / project_id
    folder.mkdir(parents=True, exist_ok=True)
    output_dir = Path(settings.render_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    width, height = (1080, 1920) if fmt == "YouTube Shorts" else (1920, 1080)
    if not scenes:
        raise RuntimeError("No scenes to render.")
    segments = []
    for index, scene in enumerate(scenes, 1):
        image = Path(scene.get("image_path") or "")
        if not image.is_file():
            image = folder / f"scene-{index}.png"
            if not image.exists():
                subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i",
                    f"color=c=0x111e2a:s={width}x{height}:d=1", "-frames:v", "1", str(image)],
                    check=True, capture_output=True)
        audio = Path(scene.get("audio_path") or "")
        segment = folder / f"segment-{index:02}.mp4"
        duration = max(2, float(scene.get("duration", 8)))
        command = [ffmpeg, "-y", "-loop", "1", "-i", str(image)]
        if audio.is_file():
            command += ["-i", str(audio)]
        command += ["-t", str(duration), "-vf",
            f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},format=yuv420p",
            "-r", "30", "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p"]
        if audio.is_file():
            command += ["-map", "0:v:0", "-map", "1:a:0", "-c:a", "aac", "-shortest"]
        else:
            command += ["-an"]
        subprocess.run(command + [str(segment)], check=True, capture_output=True)
        segments.append(segment)
    listing = folder / "concat.txt"
    listing.write_text("\n".join("file '" + path.as_posix() + "'" for path in segments), encoding="utf-8")
    output = output_dir / f"{project_id}.mp4"
    subprocess.run([ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(listing),
                    "-c", "copy", "-movflags", "+faststart", str(output)], check=True, capture_output=True)
    return "/renders/" + output.name

def mirror(project):
    if not (settings.firebase_project_id and settings.firebase_service_account_json):
        return
    try:
        from google.cloud import firestore
        from google.oauth2 import service_account
        credentials = service_account.Credentials.from_service_account_info(json.loads(settings.firebase_service_account_json))
        firestore.Client(project=settings.firebase_project_id, credentials=credentials).collection("video_projects").document(project["id"]).set(project, merge=True)
    except Exception:
        pass
