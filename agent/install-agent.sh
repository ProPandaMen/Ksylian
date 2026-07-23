#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/ksylian-agent}"
SERVICE_FILE="/etc/systemd/system/ksylian-agent.service"
PROXY_SERVICE_FILE="/etc/systemd/system/ksylian-proxy.service"

if [[ -f ".env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source ".env"
  set +a
fi

TOKEN="${KSYLIAN_AGENT_TOKEN:-}"
AGENT_HOST="${KSYLIAN_AGENT_HOST:-172.17.0.1}"
MINECRAFT_USER="${KSYLIAN_MINECRAFT_USER:-ksylian-minecraft}"
SERVER_ROOT="${KSYLIAN_SERVER_ROOT:-/opt/ksylian/servers}"

if [[ -z "$TOKEN" ]]; then
  echo "KSYLIAN_AGENT_TOKEN is required"
  exit 1
fi

sudo mkdir -p "$APP_DIR"
sudo cp ksylian_agent.py ksylian_proxy.py requirements.txt "$APP_DIR/"
sudo rm -rf "$APP_DIR/ksylian_agent_app"
sudo cp -R ksylian_agent_app "$APP_DIR/"
sudo python3 -m venv "$APP_DIR/.venv"
sudo "$APP_DIR/.venv/bin/pip" install --upgrade pip
sudo "$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt"
if ! id -u "$MINECRAFT_USER" >/dev/null 2>&1; then
  sudo useradd --system --home-dir "$SERVER_ROOT" --shell /usr/sbin/nologin "$MINECRAFT_USER"
fi
sudo mkdir -p "$SERVER_ROOT"
sudo chown "$MINECRAFT_USER:$MINECRAFT_USER" "$SERVER_ROOT"

sudo tee "$SERVICE_FILE" >/dev/null <<EOF
[Unit]
Description=Ksylian Host Agent
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$APP_DIR
Environment=KSYLIAN_AGENT_TOKEN=$TOKEN
Environment=KSYLIAN_SERVER_ROOT=$SERVER_ROOT
Environment=KSYLIAN_BACKUP_DIR=/mnt/hdd/ksylian-backups
Environment=KSYLIAN_MINECRAFT_USER=$MINECRAFT_USER
Environment=KSYLIAN_AGENT_RATE_LIMIT_REQUESTS=${KSYLIAN_AGENT_RATE_LIMIT_REQUESTS:-240}
Environment=KSYLIAN_AGENT_RATE_LIMIT_WINDOW_SECONDS=${KSYLIAN_AGENT_RATE_LIMIT_WINDOW_SECONDS:-60}
Environment=KSYLIAN_PUBLIC_DOMAIN=${KSYLIAN_PUBLIC_DOMAIN:-}
Environment=KSYLIAN_JAVA_8=${KSYLIAN_JAVA_8:-}
Environment=KSYLIAN_JAVA_17=${KSYLIAN_JAVA_17:-}
Environment=KSYLIAN_JAVA_21=${KSYLIAN_JAVA_21:-}
Environment=KSYLIAN_APP_DIR=${KSYLIAN_APP_DIR:-/opt/ksylian}
Environment=KSYLIAN_ENV_FILE=${KSYLIAN_ENV_FILE:-/opt/ksylian/deploy/.env}
Environment=KSYLIAN_COMPOSE_FILE=${KSYLIAN_COMPOSE_FILE:-/opt/ksylian/deploy/docker-compose.yml}
ExecStart=$APP_DIR/.venv/bin/uvicorn ksylian_agent:app --host $AGENT_HOST --port 8765
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

sudo tee "$PROXY_SERVICE_FILE" >/dev/null <<EOF
[Unit]
Description=Ksylian Minecraft Proxy
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$APP_DIR
Environment=KSYLIAN_DATA_DIR=${KSYLIAN_DATA_DIR:-/var/lib/ksylian-agent}
Environment=KSYLIAN_PROXY_HOST=${KSYLIAN_PROXY_HOST:-0.0.0.0}
Environment=KSYLIAN_PROXY_PORT=${KSYLIAN_PROXY_PORT:-25565}
Environment=KSYLIAN_PROXY_DOMAIN=${KSYLIAN_PROXY_DOMAIN:-${KSYLIAN_PUBLIC_DOMAIN:-}}
ExecStart=$APP_DIR/.venv/bin/python ksylian_proxy.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable ksylian-agent.service
sudo systemctl restart ksylian-agent.service
if [[ "${KSYLIAN_PROXY_ENABLED:-false}" == "true" ]]; then
  sudo systemctl enable ksylian-proxy.service
  sudo systemctl restart ksylian-proxy.service
fi
sudo systemctl status ksylian-agent.service --no-pager -l
