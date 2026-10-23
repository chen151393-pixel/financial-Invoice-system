"""回签合同上传结果：逐个文件返回真实处理结果。"""

from typing import Literal

from backend.core.dto import StrictModel


class SignedUploadItem(StrictModel):
    filename: str
    orderNumber: str = ""
    # saved 已保存（含已上传过相同文件）；unmatched 未识别单号；ambiguous 匹配多个单号；
    # conflict 已有不同文件未覆盖；failed 文件或共享盘问题
    status: Literal["saved", "unmatched", "ambiguous", "conflict", "failed"]
    reason: str
    archivePath: str | None = None


class SignedUploadResult(StrictModel):
    items: list[SignedUploadItem]
