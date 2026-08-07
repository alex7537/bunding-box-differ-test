#!/usr/bin/env bash
set -euo pipefail

DEPLOY_ROOT="${SAM21_DEPLOY_ROOT:-/share_data/zhangyurui/sam21_propagation}"
PID_FILE="$DEPLOY_ROOT/sam21_service.pid"
LOG_FILE="$DEPLOY_ROOT/logs/sam21_service.log"

if [[ -f "$PID_FILE" ]] && kill -0 "$(<"$PID_FILE")" 2>/dev/null; then
  echo "SAM2.1 service already running with PID $(<"$PID_FILE")"
  exit 0
fi

mkdir -p "$DEPLOY_ROOT/logs"
nohup "$DEPLOY_ROOT/env/bin/python" "$DEPLOY_ROOT/service/app.py" \
  --model-cfg configs/sam2.1/sam2.1_hiera_t.yaml \
  --checkpoint "$DEPLOY_ROOT/checkpoints/sam2.1_hiera_tiny.pt" \
  --allowed-root /share_data/zhangyurui \
  --host 127.0.0.1 \
  --port 5001 \
  >"$LOG_FILE" 2>&1 &
echo $! >"$PID_FILE"
echo "started SAM2.1 service with PID $(<"$PID_FILE"); log=$LOG_FILE"
