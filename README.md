# BondBook

BondBook is a private, two-person friendship scrapbook. Every memory and reflection is explicitly set to **Private**, **Draft**, or **Shared**. The FastAPI server enforces ownership and friend-connection checks for both entries and their uploaded media.

## Features

- Password-hashed, JWT-protected accounts
- One-to-one friend connection using unique invitation codes
- Memories with categories, notes, dates, tags, mood, location and privacy state
- Secure image, video, audio and browser-recorded voice-note uploads (25 MB per file by default)
- Protected media streaming: browser media is fetched using the authenticated session, never exposed as a public uploads directory
- Shared-reflection responses, notifications, searchable memories, gallery and timeline
- Mobile-first responsive interface with bottom navigation and desktop sidebar
- Light/dark theme, privacy controls, account deletion, and friend disconnection

## Requirements

- Python 3.10+
- Node.js 20+ and npm

## Setup

From the workspace root in PowerShell:

```powershell
Copy-Item .env.example .env
Copy-Item backend\.env.example backend\.env
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
cd frontend
npm.cmd install
cd ..
```

Set a unique long `SECRET_KEY` in `.env` or `backend/.env` before using the project outside local development. `backend/.env` takes precedence.

## Run

Open **two terminals** at the workspace root.

Terminal 1 — API:

```powershell
.\.venv\Scripts\Activate.ps1
uvicorn backend.main:app --reload --port 8000
```

Terminal 2 — web app:

```powershell
cd frontend
npm.cmd run dev
```

Open http://localhost:5173. The API health endpoint is http://127.0.0.1:8000/api/health.

## Local data and optional seed

SQLite data is stored as `backend/bondbook.db`; uploaded media stays in `backend/uploads/`. Both are excluded from Git. Do **not** use seed data for real users.

For a disposable local demo database only:

```powershell
.\.venv\Scripts\Activate.ps1
python backend\seed.py
```

It creates `alice@example.com` and `bob@example.com`, each with password `password123`, and one shared example memory.

## Security notes

- Passwords are bcrypt hashes, never plain text.
- All application API endpoints except registration, login, and health require a JWT bearer session.
- Entry mutation requires the owner; friend access is granted only for `Shared` entries from the connected user.
- The `/api/media/{id}` route runs the same permission check before returning a file. The uploads directory is not publicly mounted.
- Only whitelisted image/video/audio MIME types are accepted; the size limit is controlled by `MAX_UPLOAD_MB`.

## Test checklist

1. Register two different accounts and copy the first account’s invite code from Settings.
2. Sign into the second account and connect with that code.
3. Add a Private memory with files; verify it does not show up in the other account.
4. Change it to Shared and accept the confirmation; verify it appears for the connected friend and can play there.
5. Create a shared reflection from one account; reply from the other and verify the notification.
6. Test filters, gallery, timeline, disconnect, and account deletion with non-production test data.

