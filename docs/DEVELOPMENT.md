# Development setup

## Requirements
Node.js 20+, Python 3.12+, and FFmpeg on PATH (the backend Docker image includes FFmpeg).

## Local run
- Copy `.env.example` to `.env`; set `GEMINI_API_KEY` to enable real storyboard generation.
- Backend: `cd backend && python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt && uvicorn app.main:app --reload --port 8000`.
- Frontend from repository root: `npm install && npm run dev`.
- Backend tests: `cd backend && PYTHONPATH=. pytest -q`; frontend build: `npm run build`.
- Or run `docker compose up --build`.

## Architecture
The browser uses the FastAPI REST API. SQLite stores local project metadata. Gemini creates structured scenes, Imagen and Google TTS are optional asset providers, and FFmpeg assembles MP4s. Firestore mirrors metadata when configured. YouTube OAuth uses a validated state and encrypted token-at-rest storage.

## Before production
Use managed PostgreSQL, durable background jobs, object storage, shared OAuth state, per-user authentication/authorization, tenant ownership checks, rate limits, HTTPS, strict CORS, and a managed secrets service. Do not expose this starter API publicly without those controls.
