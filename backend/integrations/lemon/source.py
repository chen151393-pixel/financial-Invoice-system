"""open2 账套进项发票列表拉取与字段映射。

职责边界（见 AGENTS.md 与 docs/lemon-invoice-sync-plan.md）：本模块只做外部 HTTP 读取与
对象转换，不写数据库、不决定业务状态。落库与去重由 invoice 模块负责，任务编排由 sync
模块负责。sync 只依赖 LemonInvoiceSource 抽象接口，不依赖具体实现（后续可加 CliLemonSource）。
"""

import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Iterator, Optional

import httpx

from backend.core.errors import ApiError

from .auth import LemonOpen2Auth
from .config import LemonOpen2Settings
from .mapper import INVOICE_CATEGORY_INPUT, map_invoice, map_lines

logger = logging.getLogger("lemon.open2")


def log_failure(operation, error_type, status=None):
    logger.error(
        "lemon_open2_failed operation=%s upstream_status=%s type=%s",
        operation,
        status if status is not None else "-",
        error_type,
    )


@dataclass
class InvoiceRecord:
    """一张发票的 storage 就绪数据：票头 + 明细行（明细行不含 invoice_id，由 DAO 关联）。"""

    head: dict
    lines: list = field(default_factory=list)


class LemonInvoiceSource:
    """所有柠檬云发票来源的抽象；sync 模块依赖此接口。"""

    def pull_window(self, date_start: date, date_end: date, *, tenant: str, rows: int = 100):
        raise NotImplementedError


class Open2LemonSource(LemonInvoiceSource):
    def __init__(
        self,
        settings: LemonOpen2Settings,
        auth: LemonOpen2Auth,
        client: Optional[httpx.Client] = None,
    ):
        if settings.missing():
            raise ApiError(503, f"柠檬云 open2 配置不完整：{', '.join(settings.missing())}")
        self.settings = settings
        self.auth = auth
        self.client = client or httpx.Client(timeout=30, follow_redirects=False, trust_env=False)

    def close(self):
        self.client.close()

    def _post(self, path: str, body: dict) -> dict:
        """带 Bearer 鉴权的 POST，统一解析 open2 返回信封 State/SubState/Msg/Data。"""
        access_token = self.auth.token()
        try:
            response = self.client.post(
                f"{self.settings.api_base}{path}",
                headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
                json=body,
                follow_redirects=False,
            )
        except httpx.HTTPError:
            log_failure(path, "HTTPError")
            raise ApiError(502, "柠檬云 open2 请求失败或超时") from None
        if response.status_code == 401:
            log_failure(path, "HTTPStatusError", 401)
            raise ApiError(502, "柠檬云 open2 返回 401，token 可能失效，请重新授权")
        if not response.is_success:
            log_failure(path, "HTTPStatusError", response.status_code)
            raise ApiError(502, f"柠檬云 open2 请求未成功（HTTP {response.status_code}）")
        try:
            payload = response.json()
        except ValueError:
            log_failure(path, "InvalidJSON", response.status_code)
            raise ApiError(502, "柠檬云 open2 返回非 JSON 响应") from None
        state = payload.get("State")
        if state != 1000:
            log_failure(path, "StateNotOk", state)
            raise ApiError(502, f"柠檬云 open2 业务失败（State={state}，{payload.get('Msg')}）")
        return payload.get("Data") or {}

    def fetch_page(self, date_start: date, date_end: date, page: int, rows: int) -> list:
        """GetInvoice 单页：账套进项发票列表（invoiceCategory=10080）。"""
        # 日期范围参数名（kprqStart/kprqEnd 或 dateS/dateE）以 open2 文档为准，下方为待复核占位。
        body = {
            "invoiceCategory": INVOICE_CATEGORY_INPUT,
            "kprqStart": date_start.isoformat(),
            "kprqEnd": date_end.isoformat(),
            "page": page,
            "rows": rows,
        }
        data = self._post("/api/Invoice/Invoice/GetInvoice", body)
        # Data 可能是列表，也可能是含 list/rows/data 字段的对象；兼容处理。
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for key in ("list", "rows", "data", "items"):
                if isinstance(data.get(key), list):
                    return data[key]
        return []

    def iter_invoices(self, date_start: date, date_end: date, rows: int = 100) -> Iterator[dict]:
        """按日期窗口 + page/rows 数字分页遍历；账套内增删可能导致偏移漂移，
        由 sync 层用来源去重兜底（见设计文档 §4.1）。"""
        page = 1
        while True:
            batch = self.fetch_page(date_start, date_end, page, rows)
            if not batch:
                return
            yield from batch
            if len(batch) < rows:
                return
            page += 1

    def fetch_detail(self, raw: dict) -> Optional[list]:
        """补齐单张发票商品明细（当 GetInvoice 未内联明细时）。

        路径与参数待 open2 文档确认（其「发票」模块有“按发票代码+号码+金额/校验码+开票日期
        获得发票信息”接口）。本方法失败不抛错，返回 None，由调用方标记 detail_sync_status=pending。
        """
        if not self.settings.detail_url:
            return None
        body = {
            "fpdm": raw.get("fpdm"),
            "fphm": raw.get("fphm") or raw.get("sdphm"),
            "kprq": raw.get("kprq"),
            "je": raw.get("je"),
        }
        try:
            data = self._post(self.settings.detail_url, body)
        except ApiError:
            log_failure("detail", "BackfillFailed")
            return None
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for key in ("list", "rows", "data", "details", "mx"):
                if isinstance(data.get(key), list):
                    return data[key]
        return None

    def pull_window(
        self, date_start: date, date_end: date, *, tenant: str, rows: int = 100, now: Optional[datetime] = None
    ) -> list[InvoiceRecord]:
        """拉取一个日期窗口内的全部进项发票，补齐明细并映射为 storage 就绪结构。

        返回 InvoiceRecord 列表；sync 模块负责逐票短事务落库与来源去重。
        """
        now = now or datetime.now()
        records: list[InvoiceRecord] = []
        for raw in self.iter_invoices(date_start, date_end, rows=rows):
            details = self._inline_details(raw) or self.fetch_detail(raw)
            head = map_invoice(raw, tenant=tenant, asid=self.settings.asid, now=now)
            if details:
                head["detail_sync_status"] = "complete"
                lines = map_lines(details, tenant=tenant, now=now)
            else:
                head["detail_sync_status"] = "pending"
                lines = []
            records.append(InvoiceRecord(head=head, lines=lines))
        return records

    @staticmethod
    def _inline_details(raw: dict) -> Optional[list]:
        for key in ("details", "mx", "invoiceDetails", "items"):
            if isinstance(raw.get(key), list):
                return raw[key]
        return None
