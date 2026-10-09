"""采购合同共享盘归档；先完整写临时文件，再无覆盖地发布。"""

import hashlib
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from backend.core.errors import ApiError

CHINA_TIME = timezone(timedelta(hours=8))


def contract_filename(order_number, supplier):
    parts = []
    for value in (order_number, supplier):
        clean = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value).strip().rstrip(". ")
        if not clean or clean in {".", ".."}:
            raise ApiError(409, "子采购单编号或供应商名称缺失，无法生成合同文件名")
        parts.append(clean)
    name = "".join(parts) + ".pdf"
    if len(name.encode("utf-16-le")) // 2 > 240:
        raise ApiError(409, "合同文件名过长，请核对子采购单编号及供应商名称")
    return name


class ContractArchive:
    def __init__(self, root):
        self.root = Path(root) if root else None

    def save(self, order_number, supplier, downloaded_at, content):
        if self.root is None:
            raise ApiError(503, "合同共享盘路径尚未配置，合同未归档")
        filename = contract_filename(order_number, supplier)
        day = datetime.fromtimestamp(downloaded_at, CHINA_TIME)
        folder_name = f"{day.year}年{day.month}月{day.day}日"
        temporary = None
        digest = hashlib.sha256(content).hexdigest()

        def verify(target):
            if (
                target.stat().st_size != len(content)
                or hashlib.sha256(target.read_bytes()).hexdigest() != digest
            ):
                raise ApiError(409, "共享盘已存在同名但内容不同的合同，未覆盖；请人工核对该文件")

        try:
            root = self.root.resolve(strict=True)
            if not root.is_dir():
                raise OSError("not a directory")
            folder = root / folder_name
            folder.mkdir(exist_ok=True)
            target = (folder / filename).resolve()
            if not target.is_relative_to(root) or target.parent != folder.resolve():
                raise ApiError(409, "合同保存路径越出指定共享目录，未写入")
            if target.exists():
                verify(target)
                return str(target), filename
            temporary = folder / f".contract-{uuid.uuid4().hex}.tmp"
            with temporary.open("xb") as output:
                output.write(content)
                output.flush()
                os.fsync(output.fileno())
            try:
                if os.name == "nt":
                    # Windows/SMB 的 rename 在目标已存在时失败，不覆盖另一个下载进程的文件。
                    os.rename(temporary, target)
                else:
                    os.link(temporary, target)
            except FileExistsError:
                verify(target)
            verify(target)
            return str(target), filename
        except OSError:
            raise ApiError(503, "共享盘保存失败，请检查网络及目录写入权限；流程未推进，可重试保存") from None
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    # 只清理本次随机临时文件；共享盘断开时留待管理员清理，不删除正式文件。
                    pass
