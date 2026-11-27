import { Link, useMatch, useParams } from "react-router";
import { lazy, Suspense } from "react";
import { Skeleton } from "../shared/components/ui";
import { AppFrame } from "./WorkspaceFrame";
import { navigation } from "./navigation";
import { paths } from "./paths";
import { useViewNavigate } from "./useViewNavigate";

const ExternalGroupsPage = lazy(() =>
  import("../modules/task/pages/ExternalGroupsPage").then((m) => ({ default: m.ExternalGroupsPage })),
);
const SupplierGroupsPage = lazy(() =>
  import("../modules/task/pages/SupplierGroupsPage").then((m) => ({ default: m.SupplierGroupsPage })),
);
const SupplierOwnersPage = lazy(() =>
  import("../modules/task/pages/SupplierOwnersPage").then((m) => ({ default: m.SupplierOwnersPage })),
);
const TaskBoardPage = lazy(() =>
  import("../modules/task/pages/TaskBoardPage").then((m) => ({ default: m.TaskBoardPage })),
);
const TaskDetailPage = lazy(() =>
  import("../modules/task/pages/TaskDetailPage").then((m) => ({ default: m.TaskDetailPage })),
);

export default function TaskWorkspacePage() {
  const externalPage = useMatch(paths.externalGroups) !== null;
  const ownerPage = useMatch(paths.supplierOwners) !== null;
  const groupsPage = useMatch(paths.supplierGroups) !== null || externalPage || ownerPage;
  const { taskId } = useParams();
  const supplierTask = useMatch(`${paths.supplierTasks}/:taskId`) !== null;
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
          : ownerPage
            ? "按供应商与采购抬头维护负责人，保留人员变更与业务归属"
            : groupsPage
              ? "维护供应商的企微开票群与通知开关；关闭通知的供应商审核后不生成开票任务"
              : taskId
                ? "按任务当前节点处理合同归档、通知供应商、收票与补资料"
                : "按任务当前节点跟进合同归档、通知供应商、收票与补资料，等待最久的任务排在最前"
      }
    >
      <Suspense fallback={<Skeleton rows={5} label="正在加载页面…" />}>
        {ownerPage ? (
          <SupplierOwnersPage />
        ) : externalPage ? (
          <ExternalGroupsPage />
        ) : groupsPage ? (
          <SupplierGroupsPage />
        ) : taskId ? (
          <TaskDetailPage key={`${supplierTask}:${taskId}`} id={taskId} grouped={supplierTask} />
        ) : (
          <TaskBoardPage />
        )}
      </Suspense>
    </AppFrame>
  );
}
