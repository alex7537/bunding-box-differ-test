#!/bin/zsh
set -e

REVIEW_REPO_DIR=${0:A:h}
REVIEW_RUN_DIR="$REVIEW_REPO_DIR/downloads/parcel_sorting_annotation_latest_20260807_rerun_20260810"
REVIEW_DATASET_ROOT=${PARCEL_REVIEW_DATASET_ROOT:-/Users/zhangyurui/Downloads/new/parcel_sorting_annotation_latest_20260807/results}
REVIEW_SSH_HOST=${PARCEL_REVIEW_SSH_HOST:-yurui_dev_logistics_data_pipeline-1}
REVIEW_LOCAL_PORT=${PARCEL_REVIEW_LOCAL_PORT:-15001}
REVIEW_REMOTE_DATASET_ROOT=/share_data/zhangyurui/sam21_propagation/input/parcel_sorting_annotation_latest_20260807/results
REVIEW_TUNNEL_PID=""

sam2_health_ready() {
  curl -fsS --max-time 2 "http://127.0.0.1:$REVIEW_LOCAL_PORT/healthz" 2>/dev/null \
    | grep -q '"status":"ready"'
}

cleanup_review_tunnel() {
  if [[ -n "$REVIEW_TUNNEL_PID" ]]; then
    kill "$REVIEW_TUNNEL_PID" 2>/dev/null || true
  fi
}
trap cleanup_review_tunnel EXIT INT TERM

if sam2_health_ready; then
  echo "Reusing the healthy SAM2 tunnel on local port $REVIEW_LOCAL_PORT."
else
  if lsof -tiTCP:"$REVIEW_LOCAL_PORT" -sTCP:LISTEN >/dev/null 2>&1; then
    REVIEW_OCCUPIED_PORT=$REVIEW_LOCAL_PORT
    REVIEW_LOCAL_PORT=$("$REVIEW_REPO_DIR/.venv/bin/python" - <<'PY'
import socket
with socket.socket() as listener:
    listener.bind(("127.0.0.1", 0))
    print(listener.getsockname()[1])
PY
)
    echo "Port $REVIEW_OCCUPIED_PORT is occupied by another service; using $REVIEW_LOCAL_PORT instead."
  fi

  ssh -o ExitOnForwardFailure=yes -N \
    -L "$REVIEW_LOCAL_PORT:127.0.0.1:5001" "$REVIEW_SSH_HOST" &
  REVIEW_TUNNEL_PID=$!

  for _ in {1..40}; do
    if sam2_health_ready; then
      break
    fi
    if ! kill -0 "$REVIEW_TUNNEL_PID" 2>/dev/null; then
      echo "Failed to establish the SAM2 SSH tunnel." >&2
      exit 1
    fi
    sleep 0.25
  done
  if ! sam2_health_ready; then
    echo "The SSH tunnel started, but the SAM2 health check did not become ready." >&2
    exit 1
  fi
fi

REVIEW_GUI_ARGS=(
  --dataset-root "$REVIEW_DATASET_ROOT"
  --result-root "$REVIEW_RUN_DIR/raw_full"
  --review-root "$REVIEW_RUN_DIR/review_v4"
  --queue "$REVIEW_RUN_DIR/bbox_adjustment_queue.json"
  --service-dataset-root "$REVIEW_REMOTE_DATASET_ROOT"
  --sam2-url "http://127.0.0.1:$REVIEW_LOCAL_PORT"
  --reviewed-by zhangyurui
)
if [[ "${PARCEL_REVIEW_GUI_CHECK:-0}" == "1" ]]; then
  REVIEW_GUI_ARGS+=(--check)
fi
"$REVIEW_REPO_DIR/.venv/bin/python" "$REVIEW_REPO_DIR/tools/sam2_bbox_review_gui.py" \
  "${REVIEW_GUI_ARGS[@]}"
