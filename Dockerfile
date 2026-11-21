# Stage 1: build the buying desk
FROM node:20-alpine AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

# Stage 2: the engine and API, serving the built desk
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml README.md ./
COPY inventiq ./inventiq
RUN pip install .
COPY --from=web /web/dist ./web/dist
ENV INVENTIQ_WEB_DIST=/app/web/dist INVENTIQ_DB=/app/data/decisions.db
# train the models and draw the futures at build time, so the container starts instantly
RUN python -m inventiq build
EXPOSE 8000
CMD ["python", "-m", "inventiq", "serve", "--host", "0.0.0.0", "--port", "8000"]
