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
ROBOT_CONTROLLER=serial
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
13. For direct Raspberry Pi GPIO control with three DRI0042 drivers, wire the bench according to `../docs/raspberry-pi-dri0042-wiring.md`, then set:

```bash
ROBOT_ENABLED=true
ROBOT_CONTROLLER=gpio
ROBOT_DRIVE_SPEED=0.30
ROBOT_BRUSH_SPEED=1.00
ROBOT_BRUSH_LEAD_SECONDS=2.0
FORWARD_TIMEOUT_SECONDS=5
RETURN_TIMEOUT_SECONDS=5
```

14. Keep the dashboard pointed at the same backend host:

```bash
VITE_API_BASE_URL=http://localhost:8000
```

Use `http://raspberrypi.local:8000` or `http://<pi-ip>:8000` only when the dashboard runs on another computer.
15. Enable motor power only after upload, camera, weather, fuzzy logic, emergency stop, and GPIO wiring tests succeed.
16. To start at boot, copy `systemd/rammlah-backend.service` to `/etc/systemd/system/`, edit paths if needed, then run:

```bash
sudo systemctl daemon-reload
sudo systemctl enable rammlah-backend
sudo systemctl start rammlah-backend
```

## Raspberry Pi to DigitalOcean Upload Agent

Use this when the dashboard and AI backend are deployed on DigitalOcean, and the Raspberry Pi only needs to capture images and upload them to the cloud app.

1. In DigitalOcean App Platform, add a backend environment variable named `RASPBERRY_PI_AGENT_TOKEN`.
2. Set it to a long random value. Use the same value on the Raspberry Pi as `RAMMLAH_AGENT_TOKEN`.
3. Redeploy the DigitalOcean app.
4. Copy this repository to the Raspberry Pi.
5. Install dependencies:

```bash
cd backend
python -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
sudo apt install -y python3-picamera2
```

6. Create `backend/.env.pi-agent` from `backend/.env.pi-agent.example`:

```bash
RAMMLAH_API_BASE_URL=https://rammlah-app-d57uq.ondigitalocean.app
RAMMLAH_AGENT_TOKEN=the_same_token_from_digitalocean
RAMMLAH_SCAN_INTERVAL_SECONDS=300
LOG_LEVEL=INFO
```

7. Test one foreground run:

```bash
python pi_agent.py
```

8. To start the uploader on boot, copy `systemd/rammlah-pi-agent.service` to `/etc/systemd/system/`, edit the `WorkingDirectory`, `EnvironmentFile`, and `ExecStart` paths if your project folder is different, then run:

```bash
sudo systemctl daemon-reload
sudo systemctl enable rammlah-pi-agent
sudo systemctl start rammlah-pi-agent
sudo systemctl status rammlah-pi-agent
```

The cloud dashboard will update when the Pi uploads to `POST /api/predict/pi-upload`.

## Safety Notes

Laptop upload mode always uses `execution_mode="Test"` and never sends serial movement commands. Crack detections stop the robot and block cleaning. Weather, OpenAI, camera, fuzzy, or robot failures block cleaning and keep the FastAPI server running whenever possible.

## Tests

```bash
cd backend
pytest
```
