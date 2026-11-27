"""资料归属：整数是香港批次 ID，字符串是直接收汇报关单号，DocumentGroupRef 为资料组。只用于本模块资料表。"""

from sqlalchemy import or_

from ..dto.document_reference import DocumentGroupRef


def values(reference):
    if isinstance(reference, DocumentGroupRef):
        return {"document_group_id": reference.id}
    return {"batch_id": reference} if isinstance(reference, int) else {"direct_declaration_no": reference}


def condition(table, reference):
    field, value = next(iter(values(reference).items()))
    return table.c[field] == value


def conditions(table, references):
    """混合批次、单票与资料组共用一次读取，保持各作用域隔离。"""
    grouped = {}
    for reference in references:
        field, value = next(iter(values(reference).items()))
        grouped.setdefault(field, []).append(value)
    return or_(*(table.c[field].in_(wanted) for field, wanted in grouped.items()))


def belongs(row, reference):
    field, value = next(iter(values(reference).items()))
    return row[field] == value
