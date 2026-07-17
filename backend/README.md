# Rammlah Backend

FastAPI backend for the Rammlah Raspberry Pi 5 prototype. It accepts dashboard uploads, captures Raspberry Pi camera images, classifies solar panel condition with the OpenAI Responses API, applies weather gates, runs Mamdani fuzzy logic for dusty panels, and controls the robot only when prototype-mode safety conditions are satisfied.

## Local Setup

```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
cp .env.example .env
```

Edit `.env`:

```bash
OPENAI_API_KEY=your_key_here
LATITUDE=24.7136
LONGITUDE=46.6753
CAMERA_ENABLED=false
ROBOT_ENABLED=false
```

Start the API:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

API docs remain available at `http://localhost:8000/docs`.

## Raspberry Pi Setup

1. Copy the project to the Raspberry Pi.
2. Run `cd backend && chmod +x install_pi.sh start.sh`.
3. Run `./install_pi.sh`.
4. Edit `backend/.env`.
5. Add `OPENAI_API_KEY`.
6. Configure `LATITUDE` and `LONGITUDE`.
7. Test the camera with `python -c "from picamera2 import Picamera2; c=Picamera2(); c.start(); c.capture_file('test.jpg'); c.stop()"`.
8. Start the backend with `./start.sh`.
9. Test an uploaded image from the dashboard while `ROBOT_ENABLED=false`.
10. Test a Pi scan with `POST http://raspberrypi.local:8000/api/scan`.
11. Find the Pi IP with `hostname -I`.
12. Set dashboard `VITE_API_BASE_URL=http://raspberrypi.local:8000` or `http://<pi-ip>:8000`.
13. Enable `ROBOT_ENABLED=true` only after upload, camera, weather, fuzzy logic, emergency stop, and serial wiring tests succeed.
14. To start at boot, copy `systemd/rammlah-backend.service` to `/etc/systemd/system/`, edit paths if needed, then run:

```bash
sudo systemctl daemon-reload
sudo systemctl enable rammlah-backend
sudo systemctl start rammlah-backend
```

## Safety Notes

Laptop upload mode always uses `execution_mode="Test"` and never sends serial movement commands. Crack detections stop the robot and block cleaning. Weather, OpenAI, camera, fuzzy, or robot failures block cleaning and keep the FastAPI server running whenever possible.

## Tests

```bash
cd backend
pytest
```
