#!/usr/bin/env bash
set -euo pipefail

exec python /opt/parcel-sam2/app.py \
  --model-cfg "${SAM21_MODEL_CFG:-configs/sam2.1/sam2.1_hiera_t.yaml}" \
  --checkpoint "${SAM21_CHECKPOINT:-/models/sam2.1_hiera_tiny.pt}" \
  --allowed-root "${SAM21_ALLOWED_ROOT:-/data}" \
  --device "${SAM21_DEVICE:-cuda}" \
  --host "${SAM21_HOST:-0.0.0.0}" \
  --port "${SAM21_PORT:-5001}"
