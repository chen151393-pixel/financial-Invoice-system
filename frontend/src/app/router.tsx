import { lazy, Suspense, type ReactNode } from "react";
import { createBrowserRouter, Navigate, Outlet } from "react-router";
import { SessionProvider } from "../modules/identity/SessionProvider";
import { RequireSession } from "../modules/identity/RequireSession";
import { identityRoutes } from "../modules/identity/routes";
import { legacyPaths, paths } from "./paths";

// 各页面按需加载；新增页面只在这里登记路由。
const PlWorkspacePage = lazy(() => import("./PlWorkspacePage"));
const WorkbenchWorkspacePage = lazy(() => import("./WorkbenchWorkspacePage"));
const ReviewWorkspacePage = lazy(() => import("./ReviewWorkspacePage"));
const SyncWorkspacePage = lazy(() => import("./SyncWorkspacePage"));
const SyncBatchWorkspacePage = lazy(() => import("./SyncBatchWorkspacePage"));
const InvoiceWorkspacePage = lazy(() => import("./InvoiceWorkspacePage"));
const MatchingWorkspacePage = lazy(() => import("./MatchingWorkspacePage"));
const TaskWorkspacePage = lazy(() => import("./TaskWorkspacePage"));
const WritebackWorkspacePage = lazy(() => import("./WritebackWorkspacePage"));

function page(label: string, element: ReactNode) {
  return <Suspense fallback={<p role="status">正在加载{label}…</p>}>{element}</Suspense>;
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
          { path: paths.workbench, element: page("发票工作台", <WorkbenchWorkspacePage />) },
          { path: paths.pl, element: page("采购报关联查", <PlWorkspacePage />) },
          { path: paths.review, element: page("财务核对", <ReviewWorkspacePage />) },
          { path: legacyPaths.finance, element: <Navigate to={paths.review} replace /> },
          { path: paths.tasks, element: page("开票跟进", <TaskWorkspacePage />) },
          { path: paths.externalGroups, element: page("外部群导入与关联", <TaskWorkspacePage />) },
          { path: paths.supplierGroups, element: page("供应商档案", <TaskWorkspacePage />) },
          { path: `${paths.tasks}/:taskId`, element: page("开票任务详情", <TaskWorkspacePage />) },
          // 旧链路的任务编号在新表中不存在，旧任务详情地址统一回到任务列表。
          { path: legacyPaths.taskSupplierGroups, element: <Navigate to={paths.supplierGroups} replace /> },
          { path: legacyPaths.supplierGroups, element: <Navigate to={paths.supplierGroups} replace /> },
          { path: `${legacyPaths.invoiceFollowup}/*`, element: <Navigate to={paths.tasks} replace /> },
          { path: legacyPaths.invoiceFollowup, element: <Navigate to={paths.tasks} replace /> },
          { path: paths.invoices, element: page("进项发票", <InvoiceWorkspacePage />) },
          { path: paths.matching, element: page("发票比对", <MatchingWorkspacePage />) },
          { path: `${paths.matching}/:invoiceId`, element: page("发票比对", <MatchingWorkspacePage />) },
          { path: paths.sync, element: page("数据同步", <SyncWorkspacePage />) },
          { path: paths.syncNs, element: page("数据同步", <SyncWorkspacePage />) },
          { path: paths.syncLemon, element: page("数据同步", <SyncWorkspacePage />) },
          {
            path: `${paths.syncBatches}/:requestId`,
            element: page("同步任务详情", <SyncBatchWorkspacePage />),
          },
          { path: paths.writeback, element: page("NS 回写", <WritebackWorkspacePage />) },
          { path: `${paths.writeback}/:requestId`, element: page("NS 回写", <WritebackWorkspacePage />) },
          // 首页及未知地址进入工作台；已有业务地址保持独立访问。
          { path: "*", element: <Navigate to={paths.workbench} replace /> },
        ],
      },
    ],
  },
]);
