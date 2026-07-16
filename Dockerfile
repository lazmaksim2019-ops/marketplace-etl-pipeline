# syntax=docker.io/docker/dockerfile:1

FROM python:3.12-slim AS builder

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

FROM python:3.12-slim AS runner

WORKDIR /app

COPY --from=builder /root/.local /root/.local
COPY . .

ENV PATH=/root/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import http.client; http.client.HTTPConnection('localhost', 8000).request('GET', '/health'); assert http.client.HTTPConnection('localhost', 8000).getresponse().status == 200"

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
