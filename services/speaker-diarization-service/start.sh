#!/usr/bin/env bash
set -euo pipefail

service_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
workspace_root="$(cd "$service_root/../.." && pwd)"
cache_root="$workspace_root/models/speaker-diarization"
python_exe="${SPEAKER_DIARIZATION_PYTHON:-$service_root/.venv/bin/python}"
port="${SPEAKER_DIARIZATION_PORT:-5113}"
shared_protocol_src="$workspace_root/bobogen-protocol/src"

if [[ ! -x "$python_exe" ]]; then
  echo "Python executable not found: $python_exe. Create the service venv and install ModelScope audio dependencies first." >&2
  exit 1
fi

cd "$service_root"
export PYTHONPATH="$service_root:$shared_protocol_src"
export SPEAKER_DIARIZATION_MODEL_ID="${SPEAKER_DIARIZATION_MODEL_ID:-campplus_speaker_diarization}"
export SPEAKER_DIARIZATION_MODEL_NAME="${SPEAKER_DIARIZATION_MODEL_NAME:-iic/speech_campplus_speaker-diarization_common}"
export SPEAKER_DIARIZATION_MODEL_REVISION="${SPEAKER_DIARIZATION_MODEL_REVISION:-master}"
export SPEAKER_DIARIZATION_DEVICE="${SPEAKER_DIARIZATION_DEVICE:-cuda:0}"
export SPEAKER_DIARIZATION_PORT="$port"
export MODELSCOPE_CACHE="${MODELSCOPE_CACHE:-$cache_root/modelscope-cache}"
export MODELSCOPE_CACHE_HOME="${MODELSCOPE_CACHE_HOME:-$MODELSCOPE_CACHE}"
export TORCH_HOME="${TORCH_HOME:-$cache_root/torch-cache}"
export PIP_CACHE_DIR="${PIP_CACHE_DIR:-$cache_root/pip-cache}"

exec "$python_exe" -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port "$port"
