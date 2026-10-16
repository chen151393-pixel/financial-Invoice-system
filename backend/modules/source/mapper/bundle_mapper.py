"""逐单映射完整数据包，保留原始响应与独立核实证据，错误定位实际单据。"""

from backend.core.errors import ApiError

from ..policy.parent_reference_policy import PARENT_FIELD, document_error, supports_verification
from .ns_fields import normalize
from .storage_mapper import map_customs, map_purchases


def map_bundle(bundle, config, now):
    documents = {"customs": [], "purchase": []}
    for section, target, label, mapper in (
        ("customs", "customs", "报关单", map_customs),
        ("purchases", "purchase", "子采购单", map_purchases),
    ):
        for identity, original, lines in bundle[section]:
            record = original
            check = bundle.get("parent_reference_checks", {}).get(identity) if target == "purchase" else None
            if check and supports_verification(config.purchase) and PARENT_FIELD not in record:
                # 只为列映射补入已核实的空值；原始快照仍保留 REST 未返回字段的事实。
                record = {**record, PARENT_FIELD: None}
            try:
                mapped = mapper({**bundle, section: [(identity, record, lines)]}, config, now)[0]
            except ApiError as error:
                raise document_error(error, label, identity, original) from None
            if check:
                mapped["raw"]["record"] = normalize(original)
                mapped["raw"]["parentReferenceCheck"] = dict(check)
            documents[target].append(mapped)
    return documents
