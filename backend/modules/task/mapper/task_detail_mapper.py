"""任务详情的表格展示结构；只转换既有审核快照与资料事实，不查询或改变业务状态。"""

from ..vo.task_vo import TaskDeclarationRow, TaskPreparation, TaskReviewRow


def sections(detail):
    members = detail.memberTasks if detail.grouped else [detail.task]
    reviews, declarations = {}, {}
    for member in members:
        key = (member.recordNumber, member.reviewRevision)
        if key not in reviews:
            # 开票任务只在海关及财务审核均通过后生成；这里展示生成时的依据，不宣称来源仍有效。
            reviews[key] = (
                TaskReviewRow(
                    taskId=member.id,
                    recordNumber=member.recordNumber,
                    declarationNumber=member.declarationNumber,
                    reviewRevision=member.reviewRevision,
                    customsStatusLabel="已通过",
                    financeStatusLabel="已通过",
                    orderCount=0,
                ),
                set(),
            )
        reviews[key][1].update(member.orderNumbers)
        declarations.setdefault(
            member.recordNumber,
            TaskDeclarationRow(
                taskId=member.id,
                recordNumber=member.recordNumber,
                declarationNumber=member.declarationNumber,
            ),
        )
    detail.reviewRows = []
    for row, orders in reviews.values():
        row.orderCount = len(orders)
        detail.reviewRows.append(row)
    fields = {"customs_declaration": "customs", "sales_contract": "sales", "invoice": "invoice"}
    for doc in detail.declarationDocuments:
        record = doc.recordNumber or detail.task.recordNumber
        row = declarations.get(record)
        if row:
            setattr(row, fields[doc.type], doc)
    detail.declarationRows = list(declarations.values())
    total = len(detail.documents)
    archived = sum(doc.status == "ready" for doc in detail.documents)
    pending_signed = sum(not doc.uploaded for doc in detail.signedContracts)
    ready = total > 0 and archived == total
    detail.preparation = TaskPreparation(
        contractCount=total,
        archivedCount=archived,
        contractsReady=ready,
        contractSummary=f"{archived} / {total} 已归档" if total else "暂无子采购合同",
        declarationCount=len(declarations),
        signedPendingCount=pending_signed,
        signedSummary=f"{pending_signed} 份待补齐"
        if pending_signed
        else "回签合同已齐"
        if detail.signedContracts
        else "暂无回签合同",
        note="全部子采购合同已齐，可前往通知供应商；报关资料与回签合同在任务完结前补齐。"
        if ready
        else "请先将全部子采购合同归档；报关资料与回签合同在任务完结前补齐。",
    )
    return detail
