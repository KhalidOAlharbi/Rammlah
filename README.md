# Rammlah

Integrated Rammlah prototype with a Raspberry Pi FastAPI backend and a React dashboard.

## Start Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Set `OPENAI_API_KEY` in `backend/.env` before starting. The backend intentionally refuses to start without it.

On this Windows workspace, use the tested local port:

```powershell
.\backend\start.ps1
```

## Start Dashboard

```bash
cd dashboard
npm install
copy .env.example .env
npm run dev -- --host 0.0.0.0
```

If global `npm` is not installed, use the portable Node.js helper that was created in this workspace:

```powershell
.\dashboard\start-dev.ps1
```

For Raspberry Pi network testing, set:

```bash
VITE_API_BASE_URL=http://raspberrypi.local:8000
```

or use the Pi local IP address.
