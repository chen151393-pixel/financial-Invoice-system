"""NS机器身份签名；私钥仅在服务器使用。"""

import time

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa

from backend.core.config import Settings
from backend.core.errors import ApiError


def assertion(settings: Settings, pem: bytes, now=None):
    alg = settings.algorithm
    if alg not in ("PS256", "PS384", "PS512", "ES256", "ES384", "ES512"):
        raise ApiError(503, "不支持的 JWT 签名算法")
    try:
        key = serialization.load_pem_private_key(pem, password=None)
    except (ValueError, TypeError):
        raise ApiError(503, "无法解析 NS 私钥") from None
    curves = {"ES256": "secp256r1", "ES384": "secp384r1", "ES512": "secp521r1"}
    if alg.startswith("PS"):
        valid = isinstance(key, rsa.RSAPrivateKey) and key.key_size >= 3072
    else:
        valid = isinstance(key, ec.EllipticCurvePrivateKey) and key.curve.name == curves[alg]
    if not valid:
        raise ApiError(503, "私钥类型或长度与签名算法不匹配")
    issued = int(time.time() if now is None else now)
    return jwt.encode(
        {
            "iss": settings.client_id,
            "scope": settings.scope,
            "aud": settings.token_url,
            "iat": issued,
            "exp": issued + 300,
        },
        key,
        algorithm=alg,
        headers={"typ": "JWT", "kid": settings.certificate_id},
    )
