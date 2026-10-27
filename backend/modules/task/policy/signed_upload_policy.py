"""回签上传的传输与队列边界；文件字节不进入数据库。"""

MAX_FILE_BYTES = 100 * 1024 * 1024
CHUNK_BYTES = 4 * 1024 * 1024
MAX_FILES = 20
ACTIVE = {"uploading", "queued", "running"}
RETRYABLE = {"failed", "unmatched", "ambiguous", "conflict"}


def progress(rows):
    total = len(rows)
    finished = sum(row["status"] not in ACTIVE for row in rows)
    saved = sum(row["status"] == "saved" for row in rows)
    # 超限或空文件在建单时已被拒绝，不纳入待传输字节。
    size = sum(row["size_bytes"] for row in rows if 0 < row["size_bytes"] <= MAX_FILE_BYTES)
    received = sum(row["received_bytes"] for row in rows)
    phase = next(
        (v for v in ("running", "queued", "uploading") if any(r["status"] == v for r in rows)), "completed"
    )
    return dict(
        phase=phase,
        total=total,
        finished=finished,
        saved=saved,
        progressPercent=round(finished * 100 / total) if total else 0,
        uploadPercent=round(received * 100 / size) if size else 100,
        message=f"已处理 {finished}/{total} 个文件，已保存 {saved} 个",
    )
