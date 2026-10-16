"""连接配置与认证状态；不虚构已经运行的同步任务。"""

from datetime import datetime, timezone


class ConnectionService:
    def __init__(self, settings, ns):
        self.settings, self.ns = settings, ns
        self.last_connection = None

    def status(self):
        missing = self.settings.missing()
        return {
            "configured": not missing,
            "missing": missing,
            "account": self.settings.account,
            "writeEnabled": self.settings.write_enabled,
            "recordTypes": self.settings.record_types,
            "writeFields": self.settings.write_fields,
            "lastConnection": self.last_connection,
            "transport": "SuiteTalk REST",
        }

    def connect(self):
        self.ns.token()
        self.last_connection = {"at": datetime.now(timezone.utc).isoformat(), "authenticated": True}
        return {**self.last_connection, "message": "M2M Token 获取成功；记录读写权限需单独验证"}
