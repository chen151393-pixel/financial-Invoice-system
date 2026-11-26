"""异步文件传输的资源边界；实际明细读取不受尾部空白格式影响。"""

MAX_IMPORT_BYTES = 64 * 1024 * 1024
JSON_BODY_LIMITS = {r"/api/review/customs-receipts/import": 90 * 1024 * 1024}
