FROM m.daocloud.io/docker.io/library/node:22-bookworm-slim AS frontend

WORKDIR /src
COPY package.json package-lock.json ./
RUN npm ci
COPY web ./web
COPY public ./public
COPY scripts ./scripts
RUN npm run build

FROM m.daocloud.io/docker.io/library/python:3.11-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY backend/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
COPY backend ./backend
COPY --from=frontend /src/dist/web ./dist/web

CMD ["python", "-m", "backend"]