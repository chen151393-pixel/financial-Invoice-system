"""回签原件分片暂存；只用服务端 UUID 命名，接收完成前不归档。"""

import hashlib
import os
from pathlib import Path
from uuid import UUID

from backend.core.errors import ApiError


class SignedUploadStore:
    def __init__(self, root):
        self.root = Path(root)

    def path(self, file_id):
        name = str(UUID(file_id)) + ".upload"
        root = self.root.resolve()
        target = (root / name).resolve()
        if target.parent != root:
            raise ApiError(409, "上传暂存路径无效")
        return target

    def put(self, file_id, offset, content):
        target = self.path(file_id)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("r+b" if target.exists() else "w+b") as stream:
            stream.seek(0, os.SEEK_END)
            if stream.tell() < offset:
                raise ApiError(409, "已接收分片缺失，请重新选择文件上传")
            stream.seek(offset)
            stream.write(content)
            # 数据落盘而数据库尚未提交时，重复分片从已提交偏移重写，清除未提交尾部。
            stream.truncate()
            stream.flush()
            os.fsync(stream.fileno())

    def matches(self, file_id, offset, content):
        with self.path(file_id).open("rb") as stream:
            stream.seek(offset)
            return stream.read(len(content)) == content

    def digest(self, file_id):
        with self.path(file_id).open("rb") as stream:
            return hashlib.file_digest(stream, "sha256").hexdigest()

    def remove(self, file_id):
        self.path(file_id).unlink(missing_ok=True)
