# local-tts-service-kit

Shared FastAPI service skeleton for local TTS model services.

## Purpose

This package provides:

- a standard FastAPI app factory
- protocol routes:
  - `/v1/health`
  - `/v1/voices`
  - `/v1/synthesize`
- JSON and multipart request handling

## Install

Install into each model service environment:

```bash
pip install -e E:\AiModel\tts\local-tts-protocol
pip install -e E:\AiModel\tts\local-tts-service-kit
```
