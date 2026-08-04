#!/usr/bin/env bash
set -euo pipefail

service_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
workspace_root="$(cd "$service_root/../.." && pwd)"
model_root="$workspace_root/models/tiger"
repo_dir="$workspace_root/models/tiger/repo"
model_dir="$workspace_root/models/tiger/TIGER-DnR"
python_exe="${TIGER_DNR_PYTHON:-$service_root/.venv/bin/python}"
port="${TIGER_DNR_PORT:-5114}"

if [[ ! -x "$python_exe" ]]; then
  echo "Python executable not found: $python_exe" >&2
  exit 1
fi
if [[ ! -d "$repo_dir" ]]; then
  echo "TIGER source repository not found: $repo_dir" >&2
  exit 1
fi

export PYTHONPATH="$service_root:$workspace_root/bobogen-protocol/src:$repo_dir${PYTHONPATH:+:$PYTHONPATH}"
export TIGER_DNR_REPO_DIR="$repo_dir"
export TIGER_DNR_MODEL_DIR="${TIGER_DNR_MODEL_DIR:-$model_dir}"
export TIGER_DNR_JOB_ROOT="${TIGER_DNR_JOB_ROOT:-$model_root/runtime/jobs}"
export TIGER_DNR_HF_REPO_ID="${TIGER_DNR_HF_REPO_ID:-JusperLee/TIGER-DnR}"
export TIGER_DNR_HF_REVISION="${TIGER_DNR_HF_REVISION:-b7a59560bbca10febbcd46fb01600f868e587f57}"
export TIGER_DNR_DEVICE="${TIGER_DNR_DEVICE:-cuda:0}"
export TIGER_DNR_PORT="$port"
export HF_HOME="${HF_HOME:-$model_root/hf-home}"
export HUGGINGFACE_HUB_CACHE="${HUGGINGFACE_HUB_CACHE:-$HF_HOME/hub}"
export TORCH_HOME="${TORCH_HOME:-$model_root/torch-cache}"
export NUMBA_CACHE_DIR="${NUMBA_CACHE_DIR:-$model_root/numba-cache}"

cd "$service_root"
exec "$python_exe" -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port "$port"
