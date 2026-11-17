"""合同抬头接口：买卖双方名称、地址、电话与印章图片。"""

from fastapi import APIRouter, Path, Response

from backend.core.dependencies import Owner

from ..dto.party_dto import SavePartyRequest, UploadStampRequest
from ..vo.party_vo import Party, PartyList

PartyId = Path(ge=1)
# 印章图片以 base64 放在 JSON 中：2 MB 图片编码后约 2.7 MB
JSON_BODY_LIMITS = {r"/api/settlement/parties/\d+/stamp": 3 * 1024 * 1024}


def create_router(parties):
    router = APIRouter(prefix="/api/settlement/parties", tags=["结汇合同抬头"])

    @router.post("/query", response_model=PartyList)
    def query(owner: Owner):
        return parties.browse()

    @router.post("", response_model=Party)
    def save(body: SavePartyRequest, owner: Owner):
        return parties.save(body, owner)

    @router.post("/{party_id}/stamp", response_model=Party)
    def upload_stamp(body: UploadStampRequest, owner: Owner, party_id: int = PartyId):
        return parties.upload_stamp(party_id, body, owner)

    @router.get("/{party_id}/stamp")
    def stamp(owner: Owner, party_id: int = PartyId):
        media, content = parties.stamp(party_id)
        headers = {"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"}
        return Response(content=content, media_type=media, headers=headers)

    return router
