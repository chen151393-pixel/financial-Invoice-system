"""来源保存的数据库诊断：保留错误码与调用位置，不记录 SQL、参数或异常原文。"""

import json
import logging
import traceback
from pathlib import Path

logger = logging.getLogger("ns_api.source")
BACKEND_ROOT = Path(__file__).resolve().parents[3]


def log_database_error(error, *, operation, account, kind=None, group=()):
    original = getattr(error, "orig", None)
    args = getattr(original, "args", ())
    code = args[0] if args and type(args[0]) is int else None
    context = {
        "account": account,
        "kind": kind,
        "record_ids": [str(row.get("id", ""))[:80] for row in group[:20]],
        "group_size": len(group),
    }
    # 不使用 logger.exception / format_exception，防止驱动错误正文带出业务值。
    # 只保留项目文件名、函数和行号，不读取源码行或栈帧局部变量；
    # 过滤第三方驱动栈，避免长调用链挤掉实际 DAO 和保存流程的位置。
    frames = [
        f"{Path(frame.f_code.co_filename).name}:{line}:{frame.f_code.co_name}"
        for frame, line in traceback.walk_tb(error.__traceback__)
        if Path(frame.f_code.co_filename).resolve().is_relative_to(BACKEND_ROOT)
    ]
    logger.error(
        "ns_storage_database_error operation=%s context=%s type=%s driver_type=%s "
        "db_code=%s connection_invalidated=%s frames=%s",
        operation,
        json.dumps(context, ensure_ascii=True),
        type(error).__name__,
        type(original).__name__ if original is not None else "-",
        code if code is not None else "-",
        bool(getattr(error, "connection_invalidated", False)),
        json.dumps(frames[-12:], ensure_ascii=True),
    )
