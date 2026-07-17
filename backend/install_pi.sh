#!/usr/bin/env bash
set -euo pipefail

sudo apt update
sudo apt install -y python3-venv python3-pip python3-picamera2 libopenblas-dev

cd "$(dirname "$0")"
python3 -m venv .venv --system-site-packages
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created backend/.env. Edit OPENAI_API_KEY, LATITUDE, and LONGITUDE before starting."
fi
