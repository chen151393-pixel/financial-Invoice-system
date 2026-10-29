"""手动整单关联候选：一行一张子采购单；合计、比对与置信度均由后端计算，前端不重算。"""

from backend.core.dto import StrictModel

from .matching_vo import Check, PurchaseSide, Tier


class ManualOrderCandidate(StrictModel):
    purchaseOrderId: str
    orderNo: str
    parentOrderNo: str
    supplier: str
    company: str
    recordNumbers: list[str]
    currency: str
    # 单位或币种不同不强行相加：unit 为“多单位”时数量合计为空
    unit: str
    remainingQuantity: str | None
    remainingAmount: str | None
    orderMatched: bool
    # 按全部可分配明细的剩余应开全额与发票行做整单比对；保存时按实际填写重算
    confidence: str
    tier: Tier
    checks: list[Check]
    block: str
    # 选中后展示的明细；可分配时为全部未开完的明细，表单默认值取各行剩余应开
    lines: list[PurchaseSide]


class ManualOrderCandidates(StrictModel):
    rows: list[ManualOrderCandidate]
    total: int
