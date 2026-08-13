#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/versions.env"
CONFIG_FILE="${SAM21_CONFIG_FILE:-$SCRIPT_DIR/service.env}"
if [[ -f "$CONFIG_FILE" ]]; then
  # shellcheck disable=SC1090
  source "$CONFIG_FILE"
fi

DEPLOY_ROOT="${SAM21_DEPLOY_ROOT:-/share_data/zhangyurui/sam21_propagation}"
ENV_DIR="${SAM21_ENV_DIR:-$DEPLOY_ROOT/env}"
CHECKPOINT="${SAM21_CHECKPOINT:-$DEPLOY_ROOT/checkpoints/$SAM21_CHECKPOINT_NAME}"
APP_PATH="${SAM21_APP_PATH:-$REPO_ROOT/sam2_service/app.py}"
ALLOWED_ROOT="${SAM21_ALLOWED_ROOT:-/share_data/zhangyurui}"
HOST="${SAM21_HOST:-127.0.0.1}"
PORT="${SAM21_PORT:-5001}"
DEVICE="${SAM21_DEVICE:-cuda}"
PID_FILE="$DEPLOY_ROOT/run/sam21_service.pid"
LOG_FILE="$DEPLOY_ROOT/logs/sam21_service.log"
HEALTH_URL="http://127.0.0.1:$PORT/healthz"

owns_process() {
  [[ -f "$PID_FILE" ]] || return 1
  local pid
  pid="$(<"$PID_FILE")"
  [[ "$pid" =~ ^[0-9]+$ ]] || return 1
  kill -0 "$pid" 2>/dev/null || return 1
  ps -p "$pid" -o command= 2>/dev/null | grep -Fq -- "$APP_PATH"
}

is_running() {
  owns_process
}

is_healthy() {
  curl -fsS --max-time 3 "$HEALTH_URL" 2>/dev/null | grep -q '"status":"ready"'
}

preflight() {
  [[ -x "$ENV_DIR/bin/python" ]] || { echo "Missing environment: $ENV_DIR" >&2; return 1; }
  [[ -f "$APP_PATH" ]] || { echo "Missing service app: $APP_PATH" >&2; return 1; }
  [[ -d "$ALLOWED_ROOT" && -r "$ALLOWED_ROOT" ]] || {
    echo "Missing or unreadable allowed data root: $ALLOWED_ROOT" >&2
    return 1
  }
  [[ -f "$CHECKPOINT" ]] || { echo "Missing checkpoint: $CHECKPOINT" >&2; return 1; }
  local actual_hash
  actual_hash="$(sha256sum "$CHECKPOINT" | awk '{print $1}')"
  [[ "$actual_hash" == "$SAM21_CHECKPOINT_SHA256" ]] || {
    echo "Checkpoint checksum mismatch: $actual_hash" >&2
    return 1
  }
  "$ENV_DIR/bin/python" - "$DEVICE" "$SAM21_MODEL_CFG" <<'PY'
from importlib.resources import files
import sys
import torch
device = sys.argv[1]
if device.startswith("cuda") and not torch.cuda.is_available():
    raise SystemExit("CUDA requested but torch.cuda.is_available() is false")
from sam2.build_sam import build_sam2_video_predictor
config = files("sam2")
for part in sys.argv[2].split("/"):
    config = config.joinpath(part)
if not config.is_file():
    raise SystemExit(f"SAM2 package config is missing: {sys.argv[2]}")
PY
}

start_service() {
  if is_running; then
    if is_healthy; then
      echo "SAM2 service is already healthy (PID $(<"$PID_FILE"))"
      return
    fi
    echo "PID file points to a process but health check failed; refusing to replace it" >&2
    return 1
  fi
  if [[ -f "$PID_FILE" ]]; then
    local stale_pid
    stale_pid="$(<"$PID_FILE")"
    if [[ "$stale_pid" =~ ^[0-9]+$ ]] && kill -0 "$stale_pid" 2>/dev/null; then
      echo "PID file belongs to another live process ($stale_pid); refusing to overwrite it" >&2
      return 1
    fi
    mv "$PID_FILE" "$PID_FILE.stale.$(date +%s)"
  fi
  preflight
  mkdir -p "$DEPLOY_ROOT/logs" "$DEPLOY_ROOT/run"
  nohup "$ENV_DIR/bin/python" "$APP_PATH" \
    --model-cfg "$SAM21_MODEL_CFG" \
    --checkpoint "$CHECKPOINT" \
    --allowed-root "$ALLOWED_ROOT" \
    --device "$DEVICE" \
    --host "$HOST" \
    --port "$PORT" \
    >"$LOG_FILE" 2>&1 &
  echo $! >"$PID_FILE"
  for _ in $(seq 1 60); do
    if is_healthy; then
      echo "SAM2 service ready at $HEALTH_URL (PID $(<"$PID_FILE"))"
      return
    fi
    if ! is_running; then
      echo "SAM2 service exited during startup. Log: $LOG_FILE" >&2
      tail -n 50 "$LOG_FILE" >&2 || true
      return 1
    fi
    sleep 1
  done
  echo "SAM2 service did not become healthy. Log: $LOG_FILE" >&2
  return 1
}

stop_service() {
  if ! is_running; then
    if [[ -f "$PID_FILE" ]]; then
      local unknown_pid
      unknown_pid="$(<"$PID_FILE")"
      if [[ "$unknown_pid" =~ ^[0-9]+$ ]] && kill -0 "$unknown_pid" 2>/dev/null; then
        echo "PID file belongs to another live process ($unknown_pid); refusing to stop it" >&2
        return 1
      fi
    fi
    echo "SAM2 service is not running"
    return
  fi
  local pid
  pid="$(<"$PID_FILE")"
  kill "$pid"
  for _ in $(seq 1 20); do
    kill -0 "$pid" 2>/dev/null || { mv "$PID_FILE" "$PID_FILE.stopped.$(date +%s)"; echo "Stopped $pid"; return; }
    sleep 0.25
  done
  echo "Process $pid did not stop; no SIGKILL was sent" >&2
  return 1
}

case "${1:-status}" in
  start) start_service ;;
  stop) stop_service ;;
  restart) stop_service || true; start_service ;;
  status)
    if is_running && is_healthy; then echo "running and healthy (PID $(<"$PID_FILE"))"; else echo "not healthy"; exit 1; fi
    ;;
  health) curl -fsS "$HEALTH_URL"; echo ;;
  logs) tail -n "${SAM21_LOG_LINES:-100}" "$LOG_FILE" ;;
  *) echo "Usage: $0 {start|stop|restart|status|health|logs}" >&2; exit 2 ;;
esac
