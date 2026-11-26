"""异步导入状态与已提交的结果；接收文件不表示导入成功。"""

from typing import Literal

from backend.core.dto import StrictModel

from .customs_receipt_vo import CustomsImportResult


class CustomsImportJob(StrictModel):
    id: str
    fileName: str
    status: Literal["pending", "running", "completed", "failed"]
    statusLabel: str
    error: str
    result: CustomsImportResult | None


class CustomsImportJobs(StrictModel):
    items: list[CustomsImportJob]
