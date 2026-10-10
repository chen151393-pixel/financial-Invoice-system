"""子采购单原件的公开只读服务。"""

from backend.integrations.netsuite.subpo_contract import read_contract


class SubpoContractSource:
    def __init__(self, ns):
        self.ns = ns
        self.environment = ns.settings.account

    def unavailable_reason(self):
        settings = self.ns.settings
        if not settings.subpo_contract_script or not settings.subpo_contract_deploy:
            return "子采购合同下载接口尚未配置"
        if settings.missing():
            return "子采购合同下载连接配置不完整"
        if not {"restlets", "rest_webservices"}.issubset(settings.scope):
            return "合同下载连接需要 restlets 与 rest_webservices 授权"
        return ""

    def download(self, number, supplier, declaration):
        return read_contract(self.ns, number, supplier, declaration)
