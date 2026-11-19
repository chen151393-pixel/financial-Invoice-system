"""资料归属：整数是香港批次 ID，字符串是直接收汇报关单号。只用于本模块资料表。"""


def values(reference):
    return {"batch_id": reference} if isinstance(reference, int) else {"direct_declaration_no": reference}


def condition(table, reference):
    field, value = next(iter(values(reference).items()))
    return table.c[field] == value
