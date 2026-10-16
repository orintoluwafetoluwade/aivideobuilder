import base64
import json
import subprocess
from pathlib import Path
import httpx
from .config import settings

def integrations():
    return {
        "gemini": bool(settings.gemini_api_key),
        "imagen": bool(settings.gemini_api_key or (settings.google_cloud_project and settings.google_application_credentials)),
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
    # Normalize the configured model name so capitalization or a leading
    # "models/" prefix cannot produce an invalid Gemini REST endpoint.
    configured_model = settings.gemini_model.strip().lower()
    if configured_model.startswith("models/"):
        configured_model = configured_model[len("models/"):]
    # Gemini 2.5 Flash may return 404 for newer API projects; retry once with
    # the newer Flash-Lite model if the configured model is no longer available.
    models_to_try = [configured_model]
    if configured_model == "gemini-2.5-flash":
        models_to_try.append("gemini-3.5-flash-lite")

    async with httpx.AsyncClient(timeout=90) as client:
        response = None
        for model in models_to_try:
            candidate = await client.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                params={"key": settings.gemini_api_key},
                json={"contents": [{"parts": [{"text": prompt}]}],
                      "generationConfig": {"responseMimeType": "application/json", "temperature": 0.7}},
            )
            if candidate.status_code == 404 and model != models_to_try[-1]:
                continue
            response = candidate
            break
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
    # Try Vertex Imagen first when configured.
    if settings.google_cloud_project:
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
            if encoded:
                path.write_bytes(base64.b64decode(encoded))
                return True
        except Exception as exc:
            print(f"Vertex Imagen failed: {exc}", flush=True)

    # Use the existing Gemini API key for image generation; no Vertex credentials needed.
    if settings.gemini_api_key:
        try:
            async with httpx.AsyncClient(timeout=150) as client:
                response = await client.post(
                    "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-image:generateContent",
                    headers={"x-goog-api-key": settings.gemini_api_key},
                    json={"contents": [{"parts": [{"text": (
                        "Generate one cinematic video storyboard image. No text, lettering, captions or watermark. "
                        + prompt
                    )}]}], "generationConfig": {"responseModalities": ["IMAGE", "TEXT"]}},
                )
                response.raise_for_status()
                parts = response.json()["candidates"][0]["content"]["parts"]
            for part in parts:
                data = part.get("inlineData") or part.get("inline_data")
                if data and data.get("data"):
                    path.write_bytes(base64.b64decode(data["data"]))
                    return True
            print("Gemini image API returned no image payload.", flush=True)
        except Exception as exc:
            print(f"Gemini image generation failed: {exc}", flush=True)
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
    # Render at 720p to stay within the memory limits of small/free containers.
    width, height = (720, 1280) if fmt == "YouTube Shorts" else (1280, 720)
    if not scenes:
        raise RuntimeError("No scenes to render.")
    segments = []

    def run_ffmpeg(command, timeout):
        try:
            subprocess.run(command, check=True, capture_output=True, timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("FFmpeg timed out while rendering. Try a shorter video.") from exc
        except subprocess.CalledProcessError as exc:
            detail = (exc.stderr or b"").decode("utf-8", errors="replace")[-1200:]
            raise RuntimeError("FFmpeg could not render this video: " + (detail or str(exc))) from exc
    for index, scene in enumerate(scenes, 1):
        image = Path(scene.get("image_path") or "")
        if not image.is_file():
            image = folder / f"scene-{index}.png"
            if not image.exists():
                # Never silently create a plain blank frame when image generation fails.
                # Make a visible, labelled scene card as a last-resort fallback.
                run_ffmpeg([ffmpeg, "-y", "-f", "lavfi", "-i",
                    f"color=c=0x111e2a:s={width}x{height}:d=1",
                    "-vf", f"drawbox=x=iw*0.08:y=ih*0.08:w=iw*0.84:h=ih*0.84:color=0x1b3545:t=6,drawtext=text='SCENE {index}':fontcolor=white:fontsize=54:x=(w-text_w)/2:y=(h-text_h)/2",
                    "-frames:v", "1", str(image)], 30)
        audio = Path(scene.get("audio_path") or "")
        segment = folder / f"segment-{index:02}.mp4"
        duration = max(2, float(scene.get("duration", 8)))
        command = [ffmpeg, "-y", "-loop", "1", "-i", str(image)]
        if audio.is_file():
            command += ["-i", str(audio)]
        else:
            # Keep every segment's stream layout identical so concat also works
            # when a TTS provider is temporarily unavailable for one scene.
            command += ["-f", "lavfi", "-i",
                        f"anullsrc=channel_layout=stereo:sample_rate=44100:duration={duration}"]
        command += ["-t", str(duration), "-vf",
            f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},format=yuv420p",
            "-r", "24", "-c:v", "libx264", "-preset", "ultrafast", "-threads", "1",
            "-filter_threads", "1", "-pix_fmt", "yuv420p",
            "-map", "0:v:0", "-map", "1:a:0", "-c:a", "aac", "-ar", "44100",
            "-ac", "2", "-shortest"]
        run_ffmpeg(command + [str(segment)], int(duration) + 90)
        segments.append(segment)
    listing = folder / "concat.txt"
    listing.write_text("\n".join("file '" + path.as_posix() + "'" for path in segments), encoding="utf-8")
    output = output_dir / f"{project_id}.mp4"
    run_ffmpeg([ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(listing),
                    "-c", "copy", "-movflags", "+faststart", str(output)], 120)
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
