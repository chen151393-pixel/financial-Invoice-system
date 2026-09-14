import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from urllib.parse import parse_qs

import httpx
import jwt
import pytest
from backend.config import load_settings
from backend.netsuite import ApiError, NetSuite, assertion
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa


@pytest.fixture(scope="module")
def rsa_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=3072)


def pem(key):
    return key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )


@pytest.mark.parametrize("alg", ["PS256", "PS384", "PS512", "ES256", "ES384", "ES512"])
def test_jwt_signatures_claims_and_expiry(env, rsa_key, alg):
    curves = {"ES256": ec.SECP256R1, "ES384": ec.SECP384R1, "ES512": ec.SECP521R1}
    key = rsa_key if alg.startswith("PS") else ec.generate_private_key(curves[alg]())
    c = load_settings(
        {
            **env,
            "NETSUITE_CLIENT_ID": "client",
            "NETSUITE_CERTIFICATE_ID": "cert",
            "NETSUITE_JWT_ALGORITHM": alg,
        }
    )
    signed = assertion(c, pem(key))
    data = jwt.decode(signed, key.public_key(), algorithms=[alg], audience=c.token_url)
    assert data["iss"] == "client" and data["scope"] == ["rest_webservices"]
    assert data["exp"] - data["iat"] == 300
    assert jwt.get_unverified_header(signed)["kid"] == "cert"


def test_wrong_key_type_rejected(env, rsa_key):
    with pytest.raises(ApiError):
        assertion(replace(load_settings(env), algorithm="ES256"), pem(rsa_key))


def test_m2m_singleflight_cache_request_encoding_and_record_url(env, tmp_path, rsa_key):
    key_path = tmp_path / "private.pem"
    key_path.write_bytes(pem(rsa_key))
    c = load_settings(
        {
            **env,
            "NETSUITE_CLIENT_ID": "client",
            "NETSUITE_CERTIFICATE_ID": "cert",
            "NETSUITE_PRIVATE_KEY_PATH": str(key_path),
        }
    )
    requests = []

    def handle(request):
        requests.append(request)
        if request.url.path.endswith("/token"):
            values = parse_qs(request.content.decode())
            assert values["grant_type"] == ["client_credentials"]
            jwt.decode(
                values["client_assertion"][0],
                rsa_key.public_key(),
                algorithms=["PS256"],
                audience=c.token_url,
            )
            time.sleep(0.03)
            return httpx.Response(200, json={"access_token": "secret-token", "expires_in": 3600})
        assert request.url.host == "123456-sb1.suitetalk.api.netsuite.com"
        assert request.headers["authorization"] == "Bearer secret-token"
        return httpx.Response(204, headers={"Location": "https://example.invalid/1"})

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        ns = NetSuite(c, client)
        with ThreadPoolExecutor(4) as pool:
            assert list(pool.map(lambda _: ns.token(), range(4))) == ["secret-token"] * 4
        assert len(requests) == 1
        assert ns.request("PATCH", "vendorBill", "1", {"memo": "checked"})["status"] == 204
        assert requests[-1].url.path.endswith("/record/v1/vendorBill/1")
        assert len(requests) == 2


def test_no_redirect_or_write_retries_and_no_upstream_error_leak(env):
    c = load_settings(env)
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(
            302, headers={"Location": "https://evil.invalid"}, text="private upstream details"
        )

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        ns = NetSuite(c, client)
        with pytest.raises(ApiError) as error:
            ns.request("PATCH", "vendorBill", "1", {"memo": "checked"}, "secret")
    assert len(calls) == 1 and "private upstream" not in str(error.value)
