"""合同抬头用例：维护买卖双方名称、地址、电话与印章图片。"""

from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from backend.core import write_lock
from backend.core.errors import ApiError
from backend.core.names import normalize_name

from ..dao import party_dao
from ..dto.party_dto import MAX_STAMP_BYTES
from ..mapper.document_mapper import party
from ..vo.party_vo import PartyList
from .bill_service import decode

# 文件头 → 扩展名；只接受 PNG / JPEG
SIGNATURES = ((b"\x89PNG\r\n\x1a\n", "png"), (b"\xff\xd8\xff", "jpg"))


def _now():
    return datetime.now(UTC).replace(tzinfo=None)


def _require_operator(owner):
    if owner.startswith("service:"):
        raise ApiError(403, "服务身份只读，不能修改合同抬头")


class PartyService:
    def __init__(self, engine, store):
        self.engine, self.store = engine, store

    def browse(self):
        if self.engine is None:
            raise ApiError(503, "业务数据库未配置")
        with self.engine.connect() as connection:
            return PartyList(items=[party(row) for row in party_dao.all_parties(connection)])

    def save(self, body, owner):
        _require_operator(owner)
        key = normalize_name(body.name)
        if not key:
            raise ApiError(422, "名称不能为空")
        values = {
            "name": body.name,
            "name_key": key,
            "name_cn": body.nameCn or None,
            "name_en": body.nameEn,
            "address_cn": body.addressCn or None,
            "address_en": body.addressEn,
            "phone": body.phone or None,
            "updated_by": owner,
        }
        now = _now()
        try:
            with write_lock.transaction(self.engine, "settlement") as connection:
                if body.id is None:
                    party_id = party_dao.insert_party(connection, values, now)
                else:
                    if party_dao.get(connection, body.id) is None:
                        raise ApiError(404, "合同抬头不存在")
                    party_id = body.id
                    party_dao.update_party(connection, party_id, values, now)
                return party(party_dao.get(connection, party_id))
        except IntegrityError:
            raise ApiError(409, f"已存在同名合同抬头：{body.name}") from None
        except SQLAlchemyError:
            raise ApiError(503, "合同抬头保存失败，请检查业务数据库及迁移状态") from None

    def upload_stamp(self, party_id, body, owner):
        _require_operator(owner)
        content = decode(body.content, MAX_STAMP_BYTES, "印章图片")
        extension = next((ext for head, ext in SIGNATURES if content.startswith(head)), None)
        if extension is None:
            raise ApiError(422, "印章图片须为 PNG 或 JPG；建议使用透明底 PNG")
        file_id, sha256 = self.store.save(content, extension)
        now = _now()
        try:
            with write_lock.transaction(self.engine, "settlement") as connection:
                old = party_dao.get(connection, party_id)
                if old is None:
                    raise ApiError(404, "合同抬头不存在")
                party_dao.update_party(
                    connection,
                    party_id,
                    {
                        "stamp_file_id": file_id,
                        "stamp_sha256": sha256,
                        "stamp_extension": extension,
                        "updated_by": owner,
                    },
                    now,
                )
                result = party(party_dao.get(connection, party_id))
        except ApiError:
            self.store.remove(file_id, extension)
            raise
        except SQLAlchemyError:
            self.store.remove(file_id, extension)
            raise ApiError(503, "印章保存失败，请检查业务数据库及迁移状态") from None
        if old["stamp_file_id"]:
            self.store.remove(old["stamp_file_id"], old["stamp_extension"])
        return result

    def stamp(self, party_id):
        """返回 (媒体类型, 图片字节)。"""
        with self.engine.connect() as connection:
            row = party_dao.get(connection, party_id)
        if row is None or not row["stamp_file_id"]:
            raise ApiError(404, "该抬头尚未上传印章")
        media = "image/png" if row["stamp_extension"] == "png" else "image/jpeg"
        return media, self.store.read(row["stamp_file_id"], row["stamp_extension"])
