#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/versions.env"
CONFIG_FILE="${SAM21_CONFIG_FILE:-$SCRIPT_DIR/service.env}"
if [[ -f "$CONFIG_FILE" ]]; then
  # shellcheck disable=SC1090
  source "$CONFIG_FILE"
fi

DEPLOY_ROOT="${SAM21_DEPLOY_ROOT:-/share_data/zhangyurui/sam21_propagation}"
ENV_DIR="${SAM21_ENV_DIR:-$DEPLOY_ROOT/env}"
SOURCE_DIR="${SAM21_SAM2_SOURCE_DIR:-$DEPLOY_ROOT/vendor/sam2}"
CHECKPOINT="${SAM21_CHECKPOINT:-$DEPLOY_ROOT/checkpoints/$SAM21_CHECKPOINT_NAME}"
PYTHON_BIN="${SAM21_BOOTSTRAP_PYTHON:-python3}"

for command in git curl sha256sum; do
  command -v "$command" >/dev/null || {
    echo "Missing required command: $command" >&2
    exit 1
  }
done

"$PYTHON_BIN" - <<'PY'
import sys
if sys.version_info < (3, 10):
    raise SystemExit("Python 3.10 or newer is required")
PY

mkdir -p "$DEPLOY_ROOT/checkpoints" "$DEPLOY_ROOT/logs" "$DEPLOY_ROOT/run" \
  "$(dirname "$SOURCE_DIR")" "$(dirname "$CHECKPOINT")"

if [[ ! -d "$SOURCE_DIR/.git" ]]; then
  git clone "$SAM21_SAM2_REPOSITORY" "$SOURCE_DIR"
fi
CURRENT_REMOTE="$(git -C "$SOURCE_DIR" remote get-url origin)"
if [[ "$CURRENT_REMOTE" != "$SAM21_SAM2_REPOSITORY" ]]; then
  echo "Unexpected SAM2 remote in $SOURCE_DIR: $CURRENT_REMOTE" >&2
  exit 1
fi
git -C "$SOURCE_DIR" fetch origin "$SAM21_SAM2_COMMIT"
if [[ -n "$(git -C "$SOURCE_DIR" status --porcelain)" ]]; then
  echo "SAM2 source has local changes; refusing to change its commit: $SOURCE_DIR" >&2
  exit 1
fi
git -C "$SOURCE_DIR" checkout --detach "$SAM21_SAM2_COMMIT"

if [[ ! -x "$ENV_DIR/bin/python" ]]; then
  "$PYTHON_BIN" -m venv "$ENV_DIR"
fi
"$ENV_DIR/bin/python" -m pip install --upgrade pip setuptools wheel
"$ENV_DIR/bin/python" -m pip install \
  "torch==$SAM21_TORCH_VERSION" "torchvision==$SAM21_TORCHVISION_VERSION" \
  --index-url https://download.pytorch.org/whl/cu121
SAM2_BUILD_CUDA=0 "$ENV_DIR/bin/python" -m pip install --no-build-isolation -e "$SOURCE_DIR"
"$ENV_DIR/bin/python" -m pip install -r "$SCRIPT_DIR/../../sam2_service/requirements.txt"

if [[ -f "$CHECKPOINT" ]]; then
  CHECKPOINT_HASH="$(sha256sum "$CHECKPOINT" | awk '{print $1}')"
else
  PARTIAL_CHECKPOINT="$CHECKPOINT.partial"
  curl -fL --retry 3 "$SAM21_CHECKPOINT_URL" -o "$PARTIAL_CHECKPOINT"
  CHECKPOINT_HASH="$(sha256sum "$PARTIAL_CHECKPOINT" | awk '{print $1}')"
  if [[ "$CHECKPOINT_HASH" != "$SAM21_CHECKPOINT_SHA256" ]]; then
    echo "Checkpoint checksum mismatch: $CHECKPOINT_HASH" >&2
    exit 1
  fi
  mv "$PARTIAL_CHECKPOINT" "$CHECKPOINT"
fi
if [[ "$CHECKPOINT_HASH" != "$SAM21_CHECKPOINT_SHA256" ]]; then
  echo "Checkpoint checksum mismatch: $CHECKPOINT_HASH" >&2
  exit 1
fi

"$ENV_DIR/bin/python" - "$SAM21_MODEL_CFG" <<'PY'
from importlib.resources import files
import sys
import torch
from sam2.build_sam import build_sam2_video_predictor
config = files("sam2")
for part in sys.argv[1].split("/"):
    config = config.joinpath(part)
if not config.is_file():
    raise SystemExit(f"SAM2 package config is missing: {sys.argv[1]}")
print("torch", torch.__version__, "cuda", torch.version.cuda, "available", torch.cuda.is_available())
if not torch.cuda.is_available():
    raise SystemExit("CUDA is not available in the installed environment")
print("SAM2 import/config OK", build_sam2_video_predictor.__name__, config)
PY

echo "SAM2 environment installed in $DEPLOY_ROOT"
echo "Next: cp $SCRIPT_DIR/service.env.example $SCRIPT_DIR/service.env"
echo "Then: $SCRIPT_DIR/service.sh start"
