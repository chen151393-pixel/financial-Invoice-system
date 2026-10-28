"""批量搜索输入：保留词内空格，统一分隔符并限制查询规模。"""

import re
from typing import Annotated

from pydantic import AfterValidator, StringConstraints


def search_terms(value: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(term.strip() for term in re.split(r"[,，;；\r\n]+", value) if term.strip()))


def validate_search(value: str) -> str:
    terms = search_terms(value)
    if len(terms) > 50:
        raise ValueError("每个搜索框最多输入 50 条")
    if any(len(term) > 120 for term in terms):
        raise ValueError("每条搜索内容最多 120 个字符")
    return "\n".join(terms)


SearchText = Annotated[str, StringConstraints(max_length=6500), AfterValidator(validate_search)]
