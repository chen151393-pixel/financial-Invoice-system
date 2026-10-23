"""采购合同共享盘归档；先完整写临时文件，再无覆盖地发布。

目录（2026-10-23 业务确认）：<根目录>/<YYYY年MM月>/<CD号_真实报关单号>/子采购合同_<子采购单号>_<供应商>.pdf，
月份取 NS 报关单创建时间（中国时间）。同一报关单的其他单据以后放入同一文件夹，文件名以单据类型开头区分。
"""

import hashlib
import os
import re
import uuid
from datetime import timedelta, timezone
from pathlib import Path

from backend.core.errors import ApiError

CHINA_TIME = timezone(timedelta(hours=8))


def _clean(value):
    clean = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value or "").strip().rstrip(". ")
    return "" if clean in {".", ".."} else clean


def _bounded(name, message):
    if len(name.encode("utf-16-le")) // 2 > 240:
        raise ApiError(409, message)
    return name


def contract_filename(order_number, supplier):
    parts = [_clean(order_number), _clean(supplier)]
    if not all(parts):
        raise ApiError(409, "子采购单编号或供应商名称缺失，无法生成合同文件名")
    return _bounded(
        "子采购合同_" + "_".join(parts) + ".pdf", "合同文件名过长，请核对子采购单编号及供应商名称"
    )


def document_filename(label, record_no, index=1, count=1, extension=".pdf"):
    """报关资料、回签合同等：<单据类型>_<编号>[_序号]<扩展名>。"""
    number = _clean(record_no)
    if not number:
        raise ApiError(409, f"{label}缺少编号，无法生成文件名")
    suffix = f"_{index}" if count > 1 else ""
    return _bounded(f"{label}_{number}{suffix}{extension}", f"{label}文件名过长，请核对编号")


def declaration_folder(record_no, declaration_no):
    parts = [_clean(record_no), _clean(declaration_no)]
    if not all(parts):
        raise ApiError(409, "报关单缺少 CD 编号或真实报关单号，无法确定归档文件夹；请在 NS 补齐后重新同步")
    return _bounded("_".join(parts), "报关单文件夹名过长，请核对 CD 编号及真实报关单号")


def month_folder(created_at):
    """created_at 为 UTC 无时区时间；按中国时间取月份。"""
    if created_at is None:
        raise ApiError(409, "报关单缺少 NS 创建时间，无法确定归档月份；请重新同步该报关单后重试")
    day = created_at.replace(tzinfo=timezone.utc).astimezone(CHINA_TIME)
    return f"{day.year}年{day.month:02d}月"


class ContractArchive:
    def __init__(self, root):
        self.root = Path(root) if root else None

    def save(self, declaration, order_number, supplier, content):
        """子采购合同；返回 (完整路径, 文件名)。"""
        return self.save_file(declaration, contract_filename(order_number, supplier), content)

    def save_file(self, declaration, filename, content):
        """declaration：{record_no, declaration_no, created_at}；把一个文件存入该报关单文件夹，返回 (完整路径, 文件名)。"""
        if self.root is None:
            raise ApiError(503, "合同共享盘路径尚未配置，合同未归档")
        relative = Path(month_folder(declaration.get("created_at"))) / declaration_folder(
            declaration.get("record_no"), declaration.get("declaration_no")
        )
        temporary = None
        digest = hashlib.sha256(content).hexdigest()

        def verify(target):
            if (
                target.stat().st_size != len(content)
                or hashlib.sha256(target.read_bytes()).hexdigest() != digest
            ):
                raise ApiError(
                    409, f"共享盘已存在同名但内容不同的文件（{filename}），未覆盖；请人工核对该文件"
                )

        try:
            root = self.root.resolve(strict=True)
            if not root.is_dir():
                raise OSError("not a directory")
            folder = root / relative
            # 只在已存在的共享盘根目录下建月份与报关单两级文件夹，根目录本身不自动创建
            folder.mkdir(parents=True, exist_ok=True)
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
