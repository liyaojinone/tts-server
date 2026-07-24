#!/usr/bin/env bash
set -euo pipefail

service_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
workspace_root="$(cd "${service_root}/../.." && pwd)"
cache_root="${workspace_root}/models/qwen3-asr"
repo_dir="${cache_root}/repo"
python_exe="${QWEN3_ASR_PYTHON:-${service_root}/.venv/bin/python}"
port="${QWEN3_ASR_PORT:-5110}"
shared_protocol_src="${workspace_root}/bobogen-protocol/src"

if [[ ! -x "${python_exe}" ]]; then
  echo "Python executable not found: ${python_exe}. Create the provider-specific service environment first." >&2
  exit 1
fi

export PYTHONPATH="${service_root}:${shared_protocol_src}:${repo_dir}"
export QWEN3_ASR_REPO_DIR="${repo_dir}"
export QWEN3_ASR_MODEL_ID="${QWEN3_ASR_MODEL_ID:-qwen3_asr_0_6b}"
export QWEN3_ASR_HF_REPO_ID="${QWEN3_ASR_HF_REPO_ID:-Qwen/Qwen3-ASR-0.6B}"
export QWEN3_ASR_MODEL_DIR="${QWEN3_ASR_MODEL_DIR:-${cache_root}/Qwen3-ASR-0.6B}"
export QWEN3_ASR_DEVICE="${QWEN3_ASR_DEVICE:-cuda:0}"
export QWEN3_ASR_PORT="${port}"
export UV_CACHE_DIR="${cache_root}/uv-cache"
export PIP_CACHE_DIR="${cache_root}/pip-cache"
export HF_HOME="${cache_root}/hf-home"
export HUGGINGFACE_HUB_CACHE="${HF_HOME}/hub"
export TORCH_HOME="${cache_root}/torch-cache"

cd "${service_root}"
echo "Using Python: ${python_exe}"
echo "Qwen3-ASR repo: ${QWEN3_ASR_REPO_DIR}"
echo "Qwen3-ASR model id: ${QWEN3_ASR_MODEL_ID}"
echo "Qwen3-ASR HF repo: ${QWEN3_ASR_HF_REPO_ID}"
echo "Qwen3-ASR model dir: ${QWEN3_ASR_MODEL_DIR}"
echo "Qwen3-ASR device: ${QWEN3_ASR_DEVICE}"
echo "Starting qwen3-asr-service on http://127.0.0.1:${port}"

exec "${python_exe}" -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port "${port}"
