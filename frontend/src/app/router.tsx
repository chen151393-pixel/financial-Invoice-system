import { lazy, Suspense, type ReactNode } from "react";
import { createBrowserRouter, Navigate } from "react-router";
import { paths } from "./paths";

// 各页面按需加载；新增页面只在这里登记路由。
const PlWorkspacePage = lazy(() => import("./PlWorkspacePage"));
const FinanceWorkspacePage = lazy(() => import("./FinanceWorkspacePage"));
const SyncWorkspacePage = lazy(() => import("./SyncWorkspacePage"));
const InvoiceWorkspacePage = lazy(() => import("./InvoiceWorkspacePage"));
const MatchingWorkspacePage = lazy(() => import("./MatchingWorkspacePage"));
const InvoiceTaskWorkspacePage = lazy(() => import("./InvoiceTaskWorkspacePage"));

function page(label: string, element: ReactNode) {
  return <Suspense fallback={<p role="status">正在加载{label}…</p>}>{element}</Suspense>;
}

export const router = createBrowserRouter([
  { path: paths.pl, element: page("采购报关联查", <PlWorkspacePage />) },
  { path: paths.finance, element: page("财务核对", <FinanceWorkspacePage />) },
  { path: paths.invoiceFollowup, element: page("开票跟进", <InvoiceTaskWorkspacePage />) },
  { path: paths.supplierGroups, element: page("供应商群配置", <InvoiceTaskWorkspacePage />) },
  { path: `${paths.invoiceFollowup}/:taskId`, element: page("开票任务详情", <InvoiceTaskWorkspacePage />) },
  { path: paths.invoices, element: page("进项发票", <InvoiceWorkspacePage />) },
  { path: paths.matching, element: page("自动匹配", <MatchingWorkspacePage />) },
  { path: paths.sync, element: page("数据同步", <SyncWorkspacePage />) },
  { path: paths.syncNs, element: page("数据同步", <SyncWorkspacePage />) },
  { path: paths.syncLemon, element: page("数据同步", <SyncWorkspacePage />) },
  // 首页及未知地址（含已删除的 /demo）进入采购报关联查，并改写地址，与原行为一致。
  { path: "*", element: <Navigate to={paths.pl} replace /> },
]);
