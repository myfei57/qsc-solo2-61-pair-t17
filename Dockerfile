FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY pyproject.toml /app/pyproject.toml
COPY tunnelnet /app/tunnelnet
COPY web /app/web

RUN python -m compileall -q /app/tunnelnet

EXPOSE 8080

CMD ["python", "-m", "tunnelnet", "--store", "/data", "--web-dir", "/app/web", "--addr", "0.0.0.0:8080"]
