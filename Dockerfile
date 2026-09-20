# --- 1) 프론트엔드 빌드
FROM node:22-alpine AS web
WORKDIR /web
COPY package.json package-lock.json ./
RUN npm ci
COPY index.html tsconfig.json tsconfig.app.json tsconfig.node.json vite.config.ts ./
COPY src ./src
RUN npm run build

# --- 2) 백엔드 + 빌드된 프론트엔드를 한 서버로
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 MARINE_ENV=production MARINE_DATA_DIR=/data
WORKDIR /app/backend
COPY backend/requirements-prod.txt .
RUN pip install -r requirements-prod.txt
COPY backend/app ./app
COPY backend/data ./data
COPY --from=web /web/dist /app/dist
# DB·업로드 파일 위치(Railway 에서는 여기에 Volume 을 마운트한다)
RUN mkdir -p /data
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
