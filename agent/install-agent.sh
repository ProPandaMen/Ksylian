#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/ksylian-agent}"
SERVICE_FILE="/etc/systemd/system/ksylian-agent.service"
TOKEN="${KSYLIAN_AGENT_TOKEN:-}"

if [[ -z "$TOKEN" ]]; then
  echo "KSYLIAN_AGENT_TOKEN is required"
  exit 1
fi

sudo mkdir -p "$APP_DIR"
sudo cp ksylian_agent.py requirements.txt "$APP_DIR/"
sudo python3 -m venv "$APP_DIR/.venv"
sudo "$APP_DIR/.venv/bin/pip" install --upgrade pip
sudo "$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt"

sudo tee "$SERVICE_FILE" >/dev/null <<EOF
[Unit]
Description=Ksylian Host Agent
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$APP_DIR
Environment=KSYLIAN_AGENT_TOKEN=$TOKEN
Environment=KSYLIAN_BACKUP_DIR=/mnt/hdd/ksylian-backups
Environment=KSYLIAN_APP_DIR=${KSYLIAN_APP_DIR:-/opt/ksylian}
Environment=KSYLIAN_ENV_FILE=${KSYLIAN_ENV_FILE:-/opt/ksylian/deploy/.env}
Environment=KSYLIAN_COMPOSE_FILE=${KSYLIAN_COMPOSE_FILE:-/opt/ksylian/deploy/docker-compose.yml}
ExecStart=$APP_DIR/.venv/bin/uvicorn ksylian_agent:app --host 0.0.0.0 --port 8765
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable ksylian-agent.service
sudo systemctl restart ksylian-agent.service
sudo systemctl status ksylian-agent.service --no-pager -l
