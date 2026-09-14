import sys

import uvicorn

from .config import ROOT, load_settings


def main():
    settings = load_settings()
    if bool(settings.tls_cert) != bool(settings.tls_key):
        raise ValueError("TLS_CERT_PATH 和 TLS_KEY_PATH 必须同时配置")
    if not settings.tls_cert and settings.host not in ("127.0.0.1", "::1", "localhost"):
        raise ValueError("后端直接对外监听时必须配置 HTTPS 证书")
    if not 1 <= settings.port <= 65535:
        raise ValueError("PORT 必须在 1–65535 之间")
    uvicorn.run(
        "backend.app:create_app",
        factory=True,
        host=settings.host,
        port=settings.port,
        workers=1,
        reload="--reload" in sys.argv,
        reload_dirs=[str(ROOT / "backend")] if "--reload" in sys.argv else None,
        ssl_certfile=settings.tls_cert or None,
        ssl_keyfile=settings.tls_key or None,
        proxy_headers=False,
        access_log=False,
    )


if __name__ == "__main__":
    main()
