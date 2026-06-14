FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/bobogen-gateway:/app/bobogen-protocol/src:/app/bobogen-service-kit/src

WORKDIR /app

RUN python -m pip install --no-cache-dir --upgrade pip && \
    python -m pip install --no-cache-dir \
      fastapi \
      httpx \
      mcp \
      pydantic \
      python-multipart \
      pyyaml \
      uvicorn

COPY bobogen-gateway /app/bobogen-gateway
COPY bobogen-protocol /app/bobogen-protocol
COPY bobogen-service-kit /app/bobogen-service-kit

WORKDIR /app/bobogen-gateway
EXPOSE 6006

CMD ["python", "-m", "uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "6006"]
