"""结汇批次状态机与可操作判断（纯函数）。

香港中转：collected（香港已收）→ documents_ready（资料已出）→ settled（汇回对平，已结汇）
直接收汇：collected（已收汇）→ settled（到账对平，已结汇）
未结汇前可作废；作废后释放报关单，可重新建批次。
"""

from .route_policy import HK_TRANSIT

STATUS_LABELS = {
    "collected": "已收款",
    "documents_ready": "资料已出",
    "settled": "已结汇",
    "cancelled": "已作废",
}
HK_STATUS_LABELS = {**STATUS_LABELS, "collected": "香港已收"}

TRANSITIONS = {
    HK_TRANSIT: {
        "collected": {"documents_ready", "cancelled"},
        "documents_ready": {"settled", "cancelled"},
        "settled": set(),
        "cancelled": set(),
    },
    "direct": {
        "collected": {"settled", "cancelled"},
        "settled": set(),
        "cancelled": set(),
    },
}


def status_label(route, status):
    return (HK_STATUS_LABELS if route == HK_TRANSIT else STATUS_LABELS).get(status, status)


def can_transition(route, current, target):
    return target in TRANSITIONS.get(route, {}).get(current, set())


def _action(allowed, reason=""):
    return {"allowed": allowed, "reason": "" if allowed else reason}


def actions(batch, received_balanced, remitted_balanced):
    """各操作的 {allowed, reason}；后端执行时会再次校验。"""
    route, status = batch["route"], batch["status"]
    hk = route == HK_TRANSIT
    documents = _action(False, "仅香港中转需要出资料包")
    if hk:
        if status != "collected":
            documents = _action(False, f"当前状态为{status_label(route, status)}，不能确认资料已出")
        elif not received_balanced:
            documents = _action(False, "香港到账加手续费与报关合计不一致，请先核对金额或调整批次")
        else:
            documents = _action(True)
    if status == "settled" or status == "cancelled":
        settle = _action(False, f"批次{status_label(route, status)}")
    elif hk and status != "documents_ready":
        settle = _action(False, "香港中转须先确认资料已出，再登记汇回")
    elif hk:
        settle = _action(True)
    elif not received_balanced:
        settle = _action(False, "到账加手续费与报关合计不一致，不能确认结汇")
    else:
        settle = _action(True)
    if hk and status == "documents_ready" and remitted_balanced is False:
        settle = _action(False, "已登记的汇回金额加手续费与报关合计不一致")
    cancel = _action(can_transition(route, status, "cancelled"), "已结汇或已作废的批次不能作废")
    return {"documentsReady": documents, "settle": settle, "cancel": cancel}
