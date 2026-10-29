"""列表概况的状态分组；不改变任务状态机或允许动作。"""

GROUP_STATES = {
    "pending": ("queued", "waiting_bill", "needs_confirmation", "needs_preview", "ready"),
    "executing": ("executing",),
    "applied": ("applied",),
    "attention": ("blocked", "conflict", "partial", "unknown"),
    "stale": ("stale",),
}


def group_counts(by_state):
    return {
        "all": sum(by_state.values()),
        **{key: sum(by_state.get(state, 0) for state in states) for key, states in GROUP_STATES.items()},
    }
