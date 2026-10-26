import { Link, useMatch, useParams } from "react-router";
import { ExternalGroupsPage } from "../modules/task/pages/ExternalGroupsPage";
import { SupplierGroupsPage } from "../modules/task/pages/SupplierGroupsPage";
import { TaskBoardPage } from "../modules/task/pages/TaskBoardPage";
import { TaskDetailPage } from "../modules/task/pages/TaskDetailPage";
import { TaskListPage } from "../modules/task/pages/TaskListPage";
import { AppFrame } from "./WorkspaceFrame";
import { navigation } from "./navigation";
import { paths } from "./paths";
import { useViewNavigate } from "./useViewNavigate";

export default function TaskWorkspacePage() {
  const externalPage = useMatch(paths.externalGroups) !== null;
  const boardPage = useMatch(paths.taskBoard) !== null;
  const groupsPage = useMatch(paths.supplierGroups) !== null || externalPage;
  const { taskId } = useParams();
  const navigateView = useViewNavigate();
  return (
    <AppFrame
      groups={navigation}
      activeId={groupsPage ? "supplier-profiles" : boardPage ? "task-board" : "invoice-followup"}
      onNavigate={navigateView}
      title={
        externalPage
          ? "外部群导入与供应商关联"
          : groupsPage
            ? "供应商档案"
            : boardPage
              ? "采购开票任务台"
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
        // 外部群导入是供应商档案的下级功能，作为本页操作保留；其余跨模块跳转交给侧栏
        groupsPage && !externalPage ? (
          <Link className="ui-button ui-button--secondary" to={paths.externalGroups}>
            外部群导入与关联
          </Link>
        ) : undefined
      }
    >
      {boardPage ? (
        <TaskBoardPage />
      ) : externalPage ? (
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
