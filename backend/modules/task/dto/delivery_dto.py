"""企微通知只接受版本和服务端摘要，不接受群地址或合同路径。"""

from pydantic import Field, field_validator

from backend.core.dto import StrictModel


class DeliveryPreviewRequest(StrictModel):
    revision: int = Field(ge=1, description="已保存的通知版本")
    groupRevision: int = Field(ge=1, description="供应商默认群版本")


class DeliverySubmitRequest(DeliveryPreviewRequest):
    requestId: str = Field(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_-]+$", description="幂等编号")
    snapshotSha256: str = Field(pattern=r"^[0-9a-f]{64}$", description="服务端预览摘要")


class DeliveryRefreshRequest(StrictModel):
    deliveryId: str = Field(pattern=r"^[1-9][0-9]{0,18}$")


class DeliveryReconcileRequest(DeliveryRefreshRequest):
    candidateId: str = Field(min_length=1, max_length=190)
    evidenceSha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    reason: str = Field(min_length=1, max_length=500)

    @field_validator("reason")
    @classmethod
    def reason_required(cls, value):
        if not value.strip():
            raise ValueError("请填写核实原因")
        return value.strip()
