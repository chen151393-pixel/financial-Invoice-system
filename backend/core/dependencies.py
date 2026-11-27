"""HTTP身份依赖；业务Service不依赖Request。"""

from typing import Annotated

from fastapi import Depends, Request


def current_owner(request: Request) -> str:
    identity = request.app.state.identity
    principal = {}
    actor = identity.owner(
        authorization=request.headers.get("authorization", ""),
        session_token=request.cookies.get("ns_session"),
        method=request.method,
        origin=request.headers.get("origin"),
        principal=principal,
    )
    request.state.session_user = principal["description"]
    identity.require_api(
        actor, request.method, request.scope["route"].path, pages=request.state.session_user["pages"]
    )
    return actor


Owner = Annotated[str, Depends(current_owner)]
