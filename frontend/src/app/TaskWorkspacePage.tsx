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
      breadcrumb={
        externalPage ? (
          <Link to={paths.supplierGroups}>供应商档案</Link>
        ) : taskId ? (
          <Link to={paths.tasks}>开票跟进</Link>
        ) : undefined
      }
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
