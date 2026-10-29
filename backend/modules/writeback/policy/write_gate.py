"""写入开关、写入接口配置与供应商白名单；任一不满足时任务只停在待写入。"""


class WriteGate:
    def __init__(self, settings=None):
        self.settings = settings

    def check(self, task):
        settings = self.settings
        if settings is None or not settings.write_enabled:
            return False, "NS 写入开关未开启，方案停在待写入"
        if not settings.vendor_bill_writeback_script:
            return False, "NS 发票登记写入接口尚未配置"
        allowlist = settings.writeback_vendor_allowlist
        if allowlist != ("*",) and task["vendor_id"] not in allowlist:
            return False, "该供应商尚未列入回写白名单"
        return True, "可写入 NS"
