#!/bin/zsh
set -e

REVIEW_REPO_DIR=${0:A:h}
REVIEW_RUN_DIR="$REVIEW_REPO_DIR/downloads/parcel_sorting_annotation_latest_20260807_rerun_20260810"
REVIEW_DATASET_ROOT=${PARCEL_REVIEW_DATASET_ROOT:-/Users/zhangyurui/Downloads/new/parcel_sorting_annotation_latest_20260807/results}
REVIEW_SSH_HOST=${PARCEL_REVIEW_SSH_HOST:-yurui_dev_logistics_data_pipeline-1}
REVIEW_LOCAL_PORT=${PARCEL_REVIEW_LOCAL_PORT:-15001}
REVIEW_REMOTE_DATASET_ROOT=/share_data/zhangyurui/sam21_propagation/input/parcel_sorting_annotation_latest_20260807/results

ssh -o ExitOnForwardFailure=yes -N \
  -L "$REVIEW_LOCAL_PORT:127.0.0.1:5001" "$REVIEW_SSH_HOST" &
REVIEW_TUNNEL_PID=$!
trap 'kill "$REVIEW_TUNNEL_PID" 2>/dev/null || true' EXIT INT TERM

sleep 1
if ! kill -0 "$REVIEW_TUNNEL_PID" 2>/dev/null; then
  echo "Failed to establish the SAM2 SSH tunnel." >&2
  exit 1
fi
"$REVIEW_REPO_DIR/.venv/bin/python" "$REVIEW_REPO_DIR/tools/sam2_bbox_review_gui.py" \
  --dataset-root "$REVIEW_DATASET_ROOT" \
  --result-root "$REVIEW_RUN_DIR/raw_full" \
  --review-root "$REVIEW_RUN_DIR/review_v4" \
  --queue "$REVIEW_RUN_DIR/bbox_adjustment_queue.json" \
  --service-dataset-root "$REVIEW_REMOTE_DATASET_ROOT" \
  --sam2-url "http://127.0.0.1:$REVIEW_LOCAL_PORT" \
  --reviewed-by zhangyurui
