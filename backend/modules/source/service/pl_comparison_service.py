"""调用NS既有业务规则并核验查询JSON完整性。"""

from pydantic import ValidationError

from backend.core.errors import ApiError

from ..vo.pl_comparison import ScriptComparisonResult


class PlScriptService:
    def __init__(self, ns):
        self.ns = ns

    def query(self, criteria):
        data = self.ns.pl_script_query(criteria.model_dump())
        if isinstance(data, dict) and data.get("complete") is False:
            # 只传递脚本白名单中文错误；HTTP层不会向浏览器暴露平台原始异常。
            error = data.get("error")
            message = error.get("message") if isinstance(error, dict) else None
            request_id = data.get("requestId", "")
            if not isinstance(message, str) or len(message) > 500:
                message = "NS查询未完整完成，请联系管理员核对执行日志"
            if not isinstance(request_id, str) or len(request_id) > 100:
                request_id = ""
            raise ApiError(502, f"{message} 查询编号：{request_id}")
        try:
            result = ScriptComparisonResult.model_validate(data)
            account = result.account.lower().replace("_", "-")
            if account != self.ns.settings.account or result.query != criteria:
                raise ValueError("账户或查询范围不一致")
            if len({group.id for group in result.groups}) != len(result.groups):
                raise ValueError("重复组")
            declaration_ids = [group.declarationId for group in result.groups if group.declarationId]
            if len(set(declaration_ids)) != len(declaration_ids):
                raise ValueError("同一报关单被拆成多个审核组")
            for group in result.groups:
                if len({row.id for row in group.rows}) != len(group.rows):
                    raise ValueError("重复展示行")
                if result.contractVersion >= 2 and any(
                    row.side == "purchase" and any(row.cells[15:]) for row in group.rows
                ):
                    # 新增两列来自报关原记录，不能将其展示为采购单价或采购币种。
                    raise ValueError("采购行不应包含报关单价或币种")
                if result.contractVersion == 3:
                    customs_ids = {row.id for row in group.rows if row.side == "customs"}
                    if any(
                        row.customsRowId and (row.side != "purchase" or row.customsRowId not in customs_ids)
                        for row in group.rows
                    ):
                        raise ValueError("采购关联指向不存在的报关行")
                if group.customsCount != sum(row.side == "customs" for row in group.rows):
                    raise ValueError("报关行不完整")
                if group.purchaseCount != sum(row.side == "purchase" for row in group.rows):
                    raise ValueError("采购行不完整")
            if (
                result.counts.groups != len(result.groups)
                or result.counts.declarations != len(result.declarations)
                or result.counts.customs != sum(group.customsCount for group in result.groups)
                or result.counts.purchase != sum(group.purchaseCount for group in result.groups)
            ):
                raise ValueError("结果计数不一致")
        except (ValidationError, ValueError):
            raise ApiError(502, "NS查询结果契约或完整性校验失败，请核对两端脚本版本") from None
        # 仅标记各来源实际应提供的字段，不把报关行上的采购空栏当成缺失。
        # 不按相邻行推断配对或重算金额差异，关联及分摊结论仍来自NS。
        for group in result.groups:
            for row in group.rows:
                required = (0, 1, 2, 8, 9, 11, 12) if row.side == "customs" else (4, 5, 7, 9, 11, 12, 13, 14)
                row.missingCells = [
                    index for index in required if row.cells[index].strip() in {"", "未填写", "待确认", "—"}
                ]
        return result
