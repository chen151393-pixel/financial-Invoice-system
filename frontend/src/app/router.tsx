import { lazy, Suspense, type ReactNode } from "react";
import { createBrowserRouter, Navigate } from "react-router";
import { legacyPaths, paths } from "./paths";

// 各页面按需加载；新增页面只在这里登记路由。
const PlWorkspacePage = lazy(() => import("./PlWorkspacePage"));
const ReviewWorkspacePage = lazy(() => import("./ReviewWorkspacePage"));
const SyncWorkspacePage = lazy(() => import("./SyncWorkspacePage"));
const InvoiceWorkspacePage = lazy(() => import("./InvoiceWorkspacePage"));
const MatchingWorkspacePage = lazy(() => import("./MatchingWorkspacePage"));
const TaskWorkspacePage = lazy(() => import("./TaskWorkspacePage"));

function page(label: string, element: ReactNode) {
  return <Suspense fallback={<p role="status">正在加载{label}…</p>}>{element}</Suspense>;
}

export const router = createBrowserRouter([
  { path: paths.pl, element: page("采购报关联查", <PlWorkspacePage />) },
  { path: paths.review, element: page("财务核对", <ReviewWorkspacePage />) },
  { path: legacyPaths.finance, element: <Navigate to={paths.review} replace /> },
  { path: paths.tasks, element: page("开票跟进", <TaskWorkspacePage />) },
  { path: paths.supplierGroups, element: page("供应商群配置", <TaskWorkspacePage />) },
  { path: `${paths.tasks}/:taskId`, element: page("开票任务详情", <TaskWorkspacePage />) },
  // 旧链路的任务编号在新表中不存在，旧任务详情地址统一回到任务列表。
  { path: legacyPaths.supplierGroups, element: <Navigate to={paths.supplierGroups} replace /> },
  { path: `${legacyPaths.invoiceFollowup}/*`, element: <Navigate to={paths.tasks} replace /> },
  { path: legacyPaths.invoiceFollowup, element: <Navigate to={paths.tasks} replace /> },
  { path: paths.invoices, element: page("进项发票", <InvoiceWorkspacePage />) },
  { path: paths.matching, element: page("发票比对", <MatchingWorkspacePage />) },
  { path: `${paths.matching}/:invoiceId`, element: page("发票比对", <MatchingWorkspacePage />) },
  { path: paths.sync, element: page("数据同步", <SyncWorkspacePage />) },
  { path: paths.syncNs, element: page("数据同步", <SyncWorkspacePage />) },
  { path: paths.syncLemon, element: page("数据同步", <SyncWorkspacePage />) },
  // 首页及未知地址（含已删除的 /demo）进入采购报关联查，并改写地址，与原行为一致。
  { path: "*", element: <Navigate to={paths.pl} replace /> },
]);
