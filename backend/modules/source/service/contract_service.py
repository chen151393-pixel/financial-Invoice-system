"""NS 原件的公开只读服务：子采购合同、报关资料（报关单、销售合同、发票）。"""

from backend.integrations.netsuite import declaration_documents
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

    def declaration_unavailable_reason(self):
        if self.ns.settings.missing():
            return "报关资料下载连接配置不完整"
        return declaration_documents.unavailable_reason(self.ns.settings)

    def download_declaration(self, record_no, declaration_no, doc_type):
        """按 CD 编号与真实报关单号定位，files 每项含 content、format 和 extension。"""
        return declaration_documents.read_documents(self.ns, record_no, declaration_no, doc_type)
