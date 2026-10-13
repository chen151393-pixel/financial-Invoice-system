import { Link, useMatch, useParams } from "react-router";
import { SupplierGroupsPage } from "../modules/task/pages/SupplierGroupsPage";
import { TaskDetailPage } from "../modules/task/pages/TaskDetailPage";
import { TaskListPage } from "../modules/task/pages/TaskListPage";
import { AppFrame } from "../shared/components/AppFrame";
import { navigation } from "./navigation";
import { paths } from "./paths";
import { useViewNavigate } from "./useViewNavigate";

export default function TaskWorkspacePage() {
  const groupsPage = useMatch(paths.supplierGroups) !== null;
  const { taskId } = useParams();
  const navigateView = useViewNavigate();
  return (
    <AppFrame
      groups={navigation}
      activeId="invoice-followup"
      onNavigate={navigateView}
      title={groupsPage ? "供应商群配置" : taskId ? "开票任务详情" : "开票跟进"}
      subtitle={
        groupsPage ? "维护供应商的默认通知群及群主。" : "审核通过后自动生成任务，按供应商协作，按报关单追溯。"
      }
      mode="live"
      dataLabel={groupsPage ? "供应商群映射配置" : "审核后生成的真实任务"}
      actions={
        <div className="it-workspace-actions">
          <Link
            className="ui-button ui-button--secondary"
            to={groupsPage ? paths.tasks : paths.supplierGroups}
          >
            {groupsPage ? "返回开票跟进" : "供应商群配置"}
          </Link>
          <Link className="ui-button ui-button--secondary" to={paths.review}>
            返回财务核对
          </Link>
        </div>
      }
      notice={
        groupsPage
          ? "通过企微查询群及群主，维护供应商对应关系；通知发送接口尚未接入。"
          : "财务审核通过后按供应商、采购公司和币种自动生成任务。合同从指定 NS 环境获取并保存到共享盘；支持编辑通知并登记企微外部群人工发送；自动发送及收票比对尚未接入。"
      }
    >
      {groupsPage ? <SupplierGroupsPage /> : taskId ? <TaskDetailPage id={taskId} /> : <TaskListPage />}
    </AppFrame>
  );
}
