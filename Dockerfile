# Stage 1: Build Excalidraw Board
FROM node:20-alpine AS board-builder
WORKDIR /build
COPY board-src/package*.json ./
RUN npm ci
COPY board-src/ ./
RUN npm run build

# Stage 2: Python Backend & Complete Autonomous Runtime
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/srv/bormoclass

WORKDIR /srv/bormoclass

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Copy compiled board assets from Stage 1 into static board folder
COPY --from=board-builder /build/dist /srv/bormoclass/app/static/board/

EXPOSE 8010

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8010"]
