FROM m.daocloud.io/docker.io/library/node:22-bookworm-slim AS frontend

# 前端只依赖 frontend/ 目录：先装依赖再复制源码，利用镜像层缓存。
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
# 依赖层重建时仍可复用下载缓存；缓存仅保存在 BuildKit，不进入运行镜像。
ARG NPM_REGISTRY=https://registry.npmmirror.com
RUN --mount=type=cache,id=invoice-npm,target=/root/.npm,sharing=locked \
    npm ci --registry="$NPM_REGISTRY" --prefer-offline --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM m.daocloud.io/docker.io/library/python:3.11-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY backend/requirements.txt /tmp/requirements.txt
# 构建服务器可按网络情况指定下载源；保持锁定版本与 HTTPS 校验。
ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
ARG PIP_DEFAULT_TIMEOUT=120
ARG PIP_RETRIES=10
# 不使用 --no-cache-dir，让依赖更新时也能复用已下载的包。
RUN --mount=type=cache,id=invoice-pip,target=/root/.cache/pip,sharing=locked \
    python -m pip install --disable-pip-version-check \
    --index-url "$PIP_INDEX_URL" --timeout "$PIP_DEFAULT_TIMEOUT" --retries "$PIP_RETRIES" \
    -r /tmp/requirements.txt
COPY backend ./backend
COPY --from=frontend /src/frontend/dist ./frontend/dist

CMD ["python", "-m", "backend"]
