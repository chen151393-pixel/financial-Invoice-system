import { Link, useMatch, useParams } from "react-router";
import { ExternalGroupsPage } from "../modules/task/pages/ExternalGroupsPage";
import { SupplierGroupsPage } from "../modules/task/pages/SupplierGroupsPage";
import { TaskBoardPage } from "../modules/task/pages/TaskBoardPage";
import { TaskDetailPage } from "../modules/task/pages/TaskDetailPage";
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
      description={
        externalPage
          ? "导入企业微信外部群名单，并把群关联到供应商"
          : groupsPage
            ? "维护供应商的企微开票群与通知开关；关闭通知的供应商审核后不生成开票任务"
            : taskId
              ? "按任务当前节点处理合同归档、通知供应商、收票与补资料"
              : "按任务当前节点跟进合同归档、通知供应商、收票与补资料，等待最久的任务排在最前"
      }
    >
      {externalPage ? (
        <ExternalGroupsPage />
      ) : groupsPage ? (
        <SupplierGroupsPage />
      ) : taskId ? (
        <TaskDetailPage key={taskId} id={taskId} />
      ) : (
        <TaskBoardPage />
      )}
    </AppFrame>
  );
}
