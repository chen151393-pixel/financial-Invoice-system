import { Link, useMatch, useParams } from "react-router";
import { ExternalGroupsPage } from "../modules/task/pages/ExternalGroupsPage";
import { SupplierGroupsPage } from "../modules/task/pages/SupplierGroupsPage";
import { TaskDetailPage } from "../modules/task/pages/TaskDetailPage";
import { TaskListPage } from "../modules/task/pages/TaskListPage";
import { AppFrame } from "./WorkspaceFrame";
import { navigation } from "./navigation";
import { paths } from "./paths";
import { useViewNavigate } from "./useViewNavigate";

export default function TaskWorkspacePage() {
  const externalPage = useMatch(paths.externalGroups) !== null;
  const groupsPage = useMatch(paths.supplierGroups) !== null || externalPage;
  const { taskId } = useParams();
  const navigateView = useViewNavigate();
  return (
    <AppFrame
      groups={navigation}
      activeId={groupsPage ? "supplier-profiles" : "invoice-followup"}
      onNavigate={navigateView}
      title={
        externalPage
          ? "外部群导入与供应商关联"
          : groupsPage
            ? "供应商档案"
            : taskId
              ? "开票任务详情"
              : "开票跟进"
      }
      subtitle={
        groupsPage
          ? "按供应商名称匹配外部群，核对群主并维护默认通知对象。"
          : "审核通过后自动生成任务，按供应商协作，按报关单追溯。"
      }
      mode="live"
      dataLabel={groupsPage ? "供应商群映射配置" : "审核后生成的真实任务"}
      actions={
        <div className="it-workspace-actions">
          <Link
            className="ui-button ui-button--secondary"
            to={
              externalPage ? paths.supplierGroups : groupsPage ? paths.externalGroups : paths.supplierGroups
            }
          >
            {externalPage ? "返回供应商档案" : groupsPage ? "外部群导入与关联" : "供应商档案"}
          </Link>
          <Link className="ui-button ui-button--secondary" to={paths.review}>
            返回财务核对
          </Link>
        </div>
      }
      notice={
        groupsPage
          ? "支持 Excel 群目录导入与人工关联，也可通过企微查询群信息；群绑定用于开票任务中的通知预览。维护群信息不会发送消息。"
          : "财务审核通过后按供应商、采购公司和币种生成任务，合同归档到共享盘。通知支持提交企微群发并等待群主确认，也可登记人工发送；收票进度由发票比对确认自动汇总。"
      }
    >
      {externalPage ? (
        <ExternalGroupsPage />
      ) : groupsPage ? (
        <SupplierGroupsPage />
      ) : taskId ? (
        <TaskDetailPage key={taskId} id={taskId} />
      ) : (
        <TaskListPage />
      )}
    </AppFrame>
  );
}
