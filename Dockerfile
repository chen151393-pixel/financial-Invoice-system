FROM m.daocloud.io/docker.io/library/node:22-bookworm-slim AS frontend

# 前端只依赖 frontend/ 目录：先装依赖再复制源码，利用镜像层缓存。
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM m.daocloud.io/docker.io/library/python:3.11-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY backend/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
COPY backend ./backend
COPY --from=frontend /src/frontend/dist ./frontend/dist

CMD ["python", "-m", "backend"]