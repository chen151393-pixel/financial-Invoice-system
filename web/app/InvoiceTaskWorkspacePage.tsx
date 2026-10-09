import { InvoiceTaskDetailPage } from "../modules/reconciliation/pages/InvoiceTaskDetailPage";
import { InvoiceTaskPage } from "../modules/reconciliation/pages/InvoiceTaskPage";
import { AppFrame } from "../shared/components/AppFrame";
import { navigation } from "./navigation";
import { viewPath } from "./views";

export default function InvoiceTaskWorkspacePage() {
  const taskId = location.pathname.split("/")[2];
  return (
    <AppFrame
      groups={navigation}
      activeId="invoice-followup"
      onNavigate={(target) => location.assign(viewPath(target))}
      title={taskId ? "开票任务详情" : "开票跟进"}
      subtitle="审核通过后自动生成任务，按供应商协作，按报关单追溯。"
      mode="live"
      dataLabel="审核后生成的真实任务"
      actions={
        <a className="ui-button ui-button--secondary" href="/finance-reconciliation">
          返回财务核对
        </a>
      }
      notice="财务审核通过即可准备开票资料。合同从指定 NS 环境获取并保存到共享盘；支持编辑通知并登记企微外部群人工发送；自动发送及收票比对尚未接入。"
    >
      {taskId ? <InvoiceTaskDetailPage id={taskId} /> : <InvoiceTaskPage />}
    </AppFrame>
  );
}
