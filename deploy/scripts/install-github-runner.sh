#!/usr/bin/env bash
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/ProPandaMen/Ksylian}"
RUNNER_DIR="${RUNNER_DIR:-$HOME/actions-runner-ksylian}"
RUNNER_LABELS="${RUNNER_LABELS:-ksylian,production}"

if [[ "${1:-}" == "" ]]; then
  echo "Usage: $0 <github-runner-registration-token>"
  echo
  echo "Create a token in GitHub: Settings -> Actions -> Runners -> New self-hosted runner"
  exit 1
fi

TOKEN="$1"
ARCHIVE="actions-runner-linux-x64-2.328.0.tar.gz"
DOWNLOAD_URL="https://github.com/actions/runner/releases/download/v2.328.0/${ARCHIVE}"

mkdir -p "$RUNNER_DIR"
cd "$RUNNER_DIR"

if [[ ! -f "./config.sh" ]]; then
  curl -L -o "$ARCHIVE" "$DOWNLOAD_URL"
  tar xzf "$ARCHIVE"
  rm "$ARCHIVE"
fi

./config.sh \
  --url "$REPO_URL" \
  --token "$TOKEN" \
  --name "ilya-server-ksylian" \
  --labels "$RUNNER_LABELS" \
  --work "_work" \
  --unattended \
  --replace

sudo ./svc.sh install "$USER"
sudo ./svc.sh start
sudo ./svc.sh status

