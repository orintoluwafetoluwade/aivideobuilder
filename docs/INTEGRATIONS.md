# Integration credential checklist

## Gemini
Create a Gemini API key and set `GEMINI_API_KEY`; optionally configure `GEMINI_MODEL`. If missing, generation returns a clear 503 instead of simulating a successful AI result.

## Vertex AI Imagen
Enable Vertex AI in Google Cloud. Configure Application Default Credentials or `GOOGLE_APPLICATION_CREDENTIALS`, plus `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`, and a supported `VERTEX_IMAGEN_MODEL`. Verify model availability and IAM permissions for your project/region.

## Google Cloud Text-to-Speech
Set `GOOGLE_TTS_API_KEY` or configure Application Default Credentials with the Text-to-Speech API enabled. Select a voice using `GOOGLE_TTS_VOICE`.

## Firebase / Firestore
Set `FIREBASE_PROJECT_ID` and `FIREBASE_SERVICE_ACCOUNT_JSON` in your server secret store. Firestore is a best-effort metadata mirror; SQLite remains the local source of truth. The browser Firebase Auth SDK is not yet integrated into API access controls. Implement Firebase ID-token verification and per-user ownership before multi-user launch.

## YouTube upload
Enable YouTube Data API v3 and create a Google OAuth 2.0 Web client. Set `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`, and an authorized redirect URI exactly matching `YOUTUBE_REDIRECT_URI`. Generate a Fernet key using Python: `from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())`, then set `YOUTUBE_TOKEN_ENCRYPTION_KEY`. Set `FRONTEND_URL` for the OAuth return. OAuth state is in-memory, so replace it with shared storage for production/multiple instances. Public publishing is deliberately blocked until an explicit confirmation workflow exists.

## Secrets
Never commit API keys, service account JSON, OAuth secrets, encryption keys, or user tokens. Use hosting platform secrets or GitHub Actions secrets.
