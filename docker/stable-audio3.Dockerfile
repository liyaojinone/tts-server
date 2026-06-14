FROM nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/services/stable-audio3-service:/app/bobogen-protocol/src:/models/stable-audio-3/repo \
    STABLE_AUDIO3_REPO_DIR=/models/stable-audio-3/repo \
    STABLE_AUDIO3_MODEL_NAME=small-sfx \
    HF_HOME=/models/stable-audio-3/hf-home \
    HUGGINGFACE_HUB_CACHE=/models/stable-audio-3/hf-home/hub \
    TORCH_HOME=/models/stable-audio-3/torch-cache

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      ca-certificates \
      curl \
      ffmpeg \
      git \
      libsndfile1 \
      python3 \
      python3-pip \
      python3-venv && \
    rm -rf /var/lib/apt/lists/*

RUN python3 -m pip install --no-cache-dir --upgrade pip uv

WORKDIR /app
COPY bobogen-protocol /app/bobogen-protocol
COPY services/stable-audio3-service /app/services/stable-audio3-service

ARG STABLE_AUDIO3_REPO_URL=https://github.com/Stability-AI/stable-audio-3.git
RUN mkdir -p /models/stable-audio-3 && \
    git clone --depth 1 "$STABLE_AUDIO3_REPO_URL" /models/stable-audio-3/repo

WORKDIR /models/stable-audio-3/repo
RUN uv sync && \
    uv pip install fastapi uvicorn pydantic sentencepiece protobuf

WORKDIR /app/services/stable-audio3-service
EXPOSE 5106

CMD ["/models/stable-audio-3/repo/.venv/bin/python", "-m", "uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "5106"]
