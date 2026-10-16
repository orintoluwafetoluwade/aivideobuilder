# AI Video Studio

A premium AI-assisted YouTube production workspace built with React, TypeScript, Vite, FastAPI, Gemini, optional Vertex AI Imagen, Google Cloud Text-to-Speech, FFmpeg, Firestore metadata mirroring, and YouTube Data API upload.

## Features in this starter
- Dark, cyan-accent creator dashboard and project management.
- Gemini-backed script/storyboard generation with real provider error reporting.
- Optional Imagen scene image generation and Google Cloud TTS narration.
- FFmpeg scene assembly to landscape or vertical MP4, including audio when generated.
- SQLite project persistence and optional Firestore metadata mirror.
- YouTube OAuth callback with state validation, encrypted server-side token storage, and resumable uploads. Public uploads are blocked pending an explicit confirmation workflow.
- Docker Compose, API health checks, automated backend tests, and GitHub Actions CI.

## Quick start
1. Copy `.env.example` to `.env` and configure the providers you want.
2. Run `docker compose up --build`.
3. Open `http://localhost:5173`; API docs: `http://localhost:8000/docs`.
4. See [Development](docs/DEVELOPMENT.md) and [Integrations](docs/INTEGRATIONS.md).

## Important production limitations
This is a development foundation, not yet safe for public multi-user deployment. It currently uses SQLite and FastAPI in-process background tasks; use managed PostgreSQL, a durable queue/worker, object storage, shared OAuth/session state, per-user authentication and authorization, quotas/rate limits, HTTPS, and a secret manager before launch. Firebase Admin Firestore is an optional metadata mirror; browser-side Firebase Auth is not yet wired into API authorization. No credentials are included.

## Vercel deployment
The Vite frontend is configured for Vercel via `vercel.json`. Import this repository into Vercel, set the production branch to `main`, and add `VITE_API_BASE_URL` pointing to the publicly reachable FastAPI API base URL (including `/api`). The FastAPI backend is **not** hosted by this Vercel frontend deployment: deploy `backend/` separately to a container-capable service with FFmpeg and persistent storage, then configure its CORS origins and provider credentials. Do not deploy the SQLite/media-directory setup as a multi-user production service on Vercel serverless functions.
