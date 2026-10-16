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

## Production deployment

- **Frontend:** Vercel project `ai-video-studio`, production URL [ai-video-studio-green-chi.vercel.app](https://ai-video-studio-green-chi.vercel.app). Set `VITE_API_BASE_URL` to the deployed backend origin plus `/api`, for example `https://YOUR-BACKEND.onrender.com/api`.
- **Backend:** use the included `render.yaml` Blueprint to create a container-based Render service. It uses `backend/Dockerfile` (Python + FFmpeg) and a persistent disk for the SQLite database, generated media, rendered MP4s, and encrypted YouTube token. The persistent-disk service uses Render's paid Starter plan; do not deploy it if you do not approve that hosting cost.
- **Secrets:** when creating the Render Blueprint, supply `GEMINI_API_KEY` for script generation and a strong random `APP_SECRET`. Optional image generation needs Google Cloud project credentials; narration can use `GOOGLE_TTS_API_KEY`; YouTube upload needs the OAuth client ID/secret, a valid Fernet key, and a redirect URI exactly matching the deployed API's `/api/youtube/callback`. Add `google-credentials.json` as a Render secret file only if using Google Cloud service-account auth.
- **After backend creation:** set `VITE_API_BASE_URL=https://YOUR-BACKEND.onrender.com/api` in Vercel Production and redeploy the frontend. Set the backend `CORS_ORIGINS` and `FRONTEND_URL` to the production frontend URL.
- **Workflow:** the frontend polls project status, resolves render downloads against the backend origin, and exposes backend errors. A real storyboard requires `GEMINI_API_KEY`; image, narration, and YouTube features require their respective provider credentials.

This single-instance starter is suitable for initial validation, not an unrestricted public multi-user launch: before opening it broadly, add user authentication/ownership, rate limits and quotas, and move long renders/OAuth state to a durable queue/shared store.
