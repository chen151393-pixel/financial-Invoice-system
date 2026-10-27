"""发票文件上传结果：逐个文件返回真实处理结果。"""

from typing import Literal

from backend.core.dto import StrictModel


class InvoiceFileItem(StrictModel):
    filename: str
    invoiceNumber: str = ""
    # saved 已保存（含已上传过相同文件）；unmatched 未识别发票号码；ambiguous 匹配多张发票；
    # not_ready 发票未比对通过、已作废/红冲或子采购单未关联报关单；conflict 已有不同文件未覆盖；
    # failed 文件或共享盘问题
    status: Literal["saved", "unmatched", "ambiguous", "not_ready", "conflict", "failed"]
    reason: str
    # 发票分配到多张报关单时每个文件夹各存一份
    archivePaths: list[str] = []


class InvoiceFileResult(StrictModel):
    items: list[InvoiceFileItem]
