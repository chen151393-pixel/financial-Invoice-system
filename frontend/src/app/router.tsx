import { lazy, Suspense, type ReactNode } from "react";
import { createBrowserRouter, Navigate, Outlet, useLocation } from "react-router";
import { SessionProvider } from "../modules/identity/SessionProvider";
import { RequirePage } from "../modules/identity/RequirePage";
import { useSession } from "../modules/identity/session-context";
import { RequireSession } from "../modules/identity/RequireSession";
import { identityRoutes } from "../modules/identity/routes";
import { homePath, legacyPaths, paths, type View } from "./paths";

// 各页面按需加载；新增页面只在这里登记路由。
const PlWorkspacePage = lazy(() => import("./PlWorkspacePage"));
const WorkbenchWorkspacePage = lazy(() => import("./WorkbenchWorkspacePage"));
const ReviewWorkspacePage = lazy(() => import("./ReviewWorkspacePage"));
const CustomsMatchWorkspacePage = lazy(() => import("./CustomsMatchWorkspacePage"));
const SyncWorkspacePage = lazy(() => import("./SyncWorkspacePage"));
const SyncBatchWorkspacePage = lazy(() => import("./SyncBatchWorkspacePage"));
const SyncNsBatchWorkspacePage = lazy(() => import("./SyncNsBatchWorkspacePage"));
const InvoiceWorkspacePage = lazy(() => import("./InvoiceWorkspacePage"));
const MatchingWorkspacePage = lazy(() => import("./MatchingWorkspacePage"));
const TaskWorkspacePage = lazy(() => import("./TaskWorkspacePage"));
const WritebackWorkspacePage = lazy(() => import("./WritebackWorkspacePage"));
const RolePagesWorkspacePage = lazy(() => import("./RolePagesWorkspacePage"));
const AccessDeniedWorkspacePage = lazy(() => import("./AccessDeniedWorkspacePage"));
const AccessWorkspacePage = lazy(() => import("./AccessWorkspacePage"));
const TaskWorkflowDemoWorkspacePage = lazy(() => import("./TaskWorkflowDemoWorkspacePage"));

function page(view: View, label: string, element: ReactNode) {
  return (
    <RequirePage view={view}>
      <Suspense fallback={<p role="status">正在加载{label}…</p>}>{element}</Suspense>
    </RequirePage>
  );
}
function HomeRedirect() {
  const { user } = useSession();
  return <Navigate to={homePath(user?.pages)} replace />;
}

function TaskBoardRedirect() {
  const { search, hash } = useLocation();
  return <Navigate to={`${paths.tasks}${search}${hash}`} replace />;
}

export const router = createBrowserRouter([
  {
    element: (
      <SessionProvider>
        <Outlet />
      </SessionProvider>
    ),
    children: [
      ...identityRoutes,
      {
        element: <RequireSession />,
        children: [
          { path: paths.workbench, element: page("workbench", "总体工作台", <WorkbenchWorkspacePage />) },
          { path: paths.pl, element: page("pl", "采购报关联查", <PlWorkspacePage />) },
          { path: paths.review, element: page("finance", "财务核对", <ReviewWorkspacePage />) },
          {
            path: paths.reviewCustoms,
            element: page("customs-match", "报关单比对", <CustomsMatchWorkspacePage />),
          },
          { path: legacyPaths.finance, element: <Navigate to={paths.review} replace /> },
          { path: paths.tasks, element: page("invoice-followup", "开票跟进", <TaskWorkspacePage />) },
          {
            path: paths.supplierOwners,
            element: page("supplier-profiles", "供应商人员关联", <TaskWorkspacePage />),
          },
          { path: legacyPaths.taskBoard, element: <TaskBoardRedirect /> },
          {
            path: paths.taskWorkflowDemo,
            element: page("invoice-followup", "开票跟进优化示例", <TaskWorkflowDemoWorkspacePage />),
          },
          {
            path: paths.externalGroups,
            element: page("supplier-profiles", "外部群导入与关联", <TaskWorkspacePage />),
          },
          {
            path: paths.supplierGroups,
            element: page("supplier-profiles", "供应商档案", <TaskWorkspacePage />),
          },
          {
            path: `${paths.tasks}/:taskId`,
            element: page("invoice-followup", "开票任务详情", <TaskWorkspacePage />),
          },
          // 旧链路的任务编号在新表中不存在，旧任务详情地址统一回到任务列表。
          { path: legacyPaths.taskSupplierGroups, element: <Navigate to={paths.supplierGroups} replace /> },
          { path: legacyPaths.supplierGroups, element: <Navigate to={paths.supplierGroups} replace /> },
          { path: `${legacyPaths.invoiceFollowup}/*`, element: <Navigate to={paths.tasks} replace /> },
          { path: legacyPaths.invoiceFollowup, element: <Navigate to={paths.tasks} replace /> },
          { path: paths.invoices, element: page("invoices", "进项发票", <InvoiceWorkspacePage />) },
          { path: paths.matching, element: page("match", "发票比对", <MatchingWorkspacePage />) },
          {
            path: `${paths.matching}/:invoiceId`,
            element: page("match", "发票比对", <MatchingWorkspacePage />),
          },
          { path: paths.sync, element: page("sync", "数据同步", <SyncWorkspacePage />) },
          { path: paths.syncNs, element: page("sync", "数据同步", <SyncWorkspacePage />) },
          { path: paths.syncLemon, element: page("sync", "数据同步", <SyncWorkspacePage />) },
          {
            path: `${paths.syncBatches}/:requestId`,
            element: page("sync", "同步任务详情", <SyncBatchWorkspacePage />),
          },
          {
            path: `${paths.syncNsBatches}/:requestId`,
            element: page("sync", "NS 计划批次详情", <SyncNsBatchWorkspacePage />),
          },
          { path: paths.writeback, element: page("writeback", "NS 回写", <WritebackWorkspacePage />) },
          {
            path: `${paths.writeback}/:requestId`,
            element: page("writeback", "NS 回写", <WritebackWorkspacePage />),
          },
          { path: paths.access, element: page("access", "人员与权限", <AccessWorkspacePage />) },
          { path: paths.rolePages, element: page("access", "角色管理", <RolePagesWorkspacePage />) },
          {
            path: paths.forbidden,
            element: (
              <Suspense fallback={<p role="status">正在加载权限提示…</p>}>
                <AccessDeniedWorkspacePage />
              </Suspense>
            ),
          },
          // 首页及未知地址优先进入总体工作台，未授权时使用其他可访问页面。
          { path: "*", element: <HomeRedirect /> },
        ],
      },
    ],
  },
]);
