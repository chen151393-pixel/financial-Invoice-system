import { InvoiceTaskDetailPage } from "../modules/reconciliation/pages/InvoiceTaskDetailPage";
import { InvoiceTaskPage } from "../modules/reconciliation/pages/InvoiceTaskPage";
import { SupplierGroupsPage } from "../modules/reconciliation/pages/SupplierGroupsPage";
import { AppFrame } from "../shared/components/AppFrame";
import { navigation } from "./navigation";
import { viewPath } from "./views";

export default function InvoiceTaskWorkspacePage() {
  const groupsPage = location.pathname === "/invoice-followup/supplier-groups";
  const taskId = groupsPage ? undefined : location.pathname.split("/")[2];
  return (
    <AppFrame
      groups={navigation}
      activeId="invoice-followup"
      onNavigate={(target) => location.assign(viewPath(target))}
      title={groupsPage ? "供应商群配置" : taskId ? "开票任务详情" : "开票跟进"}
      subtitle={
        groupsPage ? "维护供应商的默认通知群及群主。" : "审核通过后自动生成任务，按供应商协作，按报关单追溯。"
      }
      mode="live"
      dataLabel={groupsPage ? "供应商群映射配置" : "审核后生成的真实任务"}
      actions={
        <div className="it-workspace-actions">
          <a
            className="ui-button ui-button--secondary"
            href={groupsPage ? "/invoice-followup" : "/invoice-followup/supplier-groups"}
          >
            {groupsPage ? "返回开票跟进" : "供应商群配置"}
          </a>
          <a className="ui-button ui-button--secondary" href="/finance-reconciliation">
            返回财务核对
          </a>
        </div>
      }
      notice={
        groupsPage
          ? "通过企微查询群及群主，维护供应商对应关系；通知发送接口尚未接入。"
          : "财务审核通过即可准备开票资料。合同从指定 NS 环境获取并保存到共享盘；支持编辑通知并登记企微外部群人工发送；自动发送及收票比对尚未接入。"
      }
    >
      {groupsPage ? (
        <SupplierGroupsPage />
      ) : taskId ? (
        <InvoiceTaskDetailPage id={taskId} />
      ) : (
        <InvoiceTaskPage />
      )}
    </AppFrame>
  );
}
