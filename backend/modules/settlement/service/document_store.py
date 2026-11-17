"""结汇资料文件存放：提单、生成的销售合同、印章图片。只用服务端生成的 UUID 命名，数据库记录标识与校验值。"""

import hashlib
import os
from pathlib import Path
from uuid import UUID, uuid4

from backend.core.errors import ApiError


class DocumentStore:
    def __init__(self, root):
        self.root = Path(root) if root else None

    def path(self, file_id, extension):
        if self.root is None:
            raise ApiError(503, "结汇资料目录尚未配置")
        if extension not in ("pdf", "png", "jpg"):
            raise ApiError(409, "结汇资料文件类型无效")
        root = self.root.resolve()
        target = (root / f"{UUID(file_id)}.{extension}").resolve()
        if target.parent != root:
            raise ApiError(409, "结汇资料文件路径无效")
        return target

    def save(self, content, extension):
        """写入新文件并落盘；返回 (文件标识, SHA-256)。数据库写入失败时由调用方 remove。"""
        file_id = str(uuid4())
        target = self.path(file_id, extension)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
        except OSError:
            raise ApiError(503, "结汇资料保存失败，请检查资料目录是否可写") from None
        return file_id, hashlib.sha256(content).hexdigest()

    def read(self, file_id, extension):
        try:
            return self.path(file_id, extension).read_bytes()
        except OSError:
            raise ApiError(404, "资料文件不存在或无法读取，请重新上传或重新生成") from None

    def remove(self, file_id, extension):
        try:
            self.path(file_id, extension).unlink(missing_ok=True)
        except OSError:
            # 清理失败只留下无引用文件，不影响业务结果
            pass
