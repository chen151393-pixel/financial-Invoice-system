"""应收看板查询：按财务审核通过的开票月份、采购员、采购抬头、供应商与单号筛选。"""

from typing import Literal

from pydantic import Field

from backend.core.dto import StrictModel
from backend.core.search_terms import SearchText


class RecoveryQuery(StrictModel):
    # 空为默认月份（北京时间当前月份）；all 为全部月份；否则为 YYYY-MM
    month: str = Field(default="", pattern=r"^(all|[0-9]{4}-(0[1-9]|1[0-2]))?$")
    # 清单内容随卡片切换：due 应收回、collected 已收回、outstanding 未收回、overdue 逾期未收回
    view: Literal["due", "collected", "outstanding", "overdue"] = "outstanding"
    # 采购员：空为全部；none 为未指定负责人的供应商
    memberId: str = Field(default="", pattern=r"^(none|[1-9][0-9]{0,19})?$")
    companyId: str = Field(default="", pattern=r"^([1-9][0-9]{0,19})?$")
    # 供应商名称与 CD 号 / 子采购单号：部分匹配，多个用逗号或换行分隔
    supplierName: SearchText = ""
    orderNo: SearchText = ""
    page: int = Field(default=1, ge=1, le=100000)
    pageSize: int = Field(default=10, ge=1, le=50)
