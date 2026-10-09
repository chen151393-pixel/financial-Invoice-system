"""HTTP身份依赖；业务Service不依赖Request。"""

from typing import Annotated

from fastapi import Depends, Request


def current_owner(request: Request) -> str:
    return request.app.state.identity.owner(
        authorization=request.headers.get("authorization", ""),
        session_token=request.cookies.get("ns_session"),
        method=request.method,
        origin=request.headers.get("origin"),
    )


Owner = Annotated[str, Depends(current_owner)]
