"""销售合同生成请求：卖方抬头与条款由经办人确认；金额、日期、口岸由后端按规则取数，不接受前端提交。"""

from typing import Annotated

from pydantic import Field, StringConstraints

from backend.core.dto import StrictModel

Terms = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]


class GenerateContractsRequest(StrictModel):
    sellerPartyId: int = Field(ge=1)
    tradeTerm: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=20)] = "FOB"
    paymentTermsCn: Terms
    paymentTermsEn: Terms
