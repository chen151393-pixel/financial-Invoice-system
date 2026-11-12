"""HTTP身份依赖；业务Service不依赖Request。"""

from typing import Annotated

from fastapi import Depends, Request


def current_owner(request: Request) -> str:
    identity = request.app.state.identity
    actor = identity.owner(
        authorization=request.headers.get("authorization", ""),
        session_token=request.cookies.get("ns_session"),
        method=request.method,
        origin=request.headers.get("origin"),
    )
    identity.require_api(actor, request.method, request.scope["route"].path)
    return actor


Owner = Annotated[str, Depends(current_owner)]
