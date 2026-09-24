import { lazy, Suspense } from "react";

// 演示包仅在/demo加载，正式页面不加载原型数据或样式。
const DemoPage = lazy(() => import("./DemoPage"));
const PlWorkspacePage = lazy(() => import("./PlWorkspacePage"));
const FinanceWorkspacePage = lazy(() => import("./FinanceWorkspacePage"));
const SyncWorkspacePage = lazy(() => import("./SyncWorkspacePage"));
const InvoiceWorkspacePage = lazy(() => import("./InvoiceWorkspacePage"));
const MatchingWorkspacePage = lazy(() => import("./MatchingWorkspacePage"));
const InvoiceTaskWorkspacePage = lazy(() => import("./InvoiceTaskWorkspacePage"));
export default function App() {
  if (location.pathname === "/invoice-followup" || location.pathname.startsWith("/invoice-followup/"))
    return (
      <Suspense fallback={<p role="status">正在加载开票跟进…</p>}>
        <InvoiceTaskWorkspacePage />
      </Suspense>
    );
  if (
    location.pathname === "/finance-reconciliation" ||
    (location.pathname === "/demo" && new URLSearchParams(location.search).get("view") === "finance")
  )
    return (
      <Suspense fallback={<p role="status">正在加载财务核对…</p>}>
        <FinanceWorkspacePage />
      </Suspense>
    );
  if (location.pathname === "/matching")
    return (
      <Suspense fallback={<p role="status">正在加载自动匹配…</p>}>
        <MatchingWorkspacePage />
      </Suspense>
    );
  if (
    location.pathname === "/invoices" ||
    (location.pathname === "/demo" && new URLSearchParams(location.search).get("view") === "invoices")
  )
    return (
      <Suspense fallback={<p role="status">正在加载进项发票…</p>}>
        <InvoiceWorkspacePage />
      </Suspense>
    );
  if (
    ["/sync", "/sync/ns", "/sync/lemon"].includes(location.pathname) ||
    (location.pathname === "/demo" && new URLSearchParams(location.search).get("view") === "sync")
  )
    return (
      <Suspense fallback={<p role="status">正在加载数据同步…</p>}>
        <SyncWorkspacePage />
      </Suspense>
    );
  const isPlPage = location.pathname !== "/demo" || new URLSearchParams(location.search).get("view") === "pl";
  if (isPlPage)
    return (
      <Suspense fallback={<p role="status">正在加载采购报关联查…</p>}>
        <PlWorkspacePage />
      </Suspense>
    );
  return (
    <Suspense fallback={<p role="status">正在加载演示…</p>}>
      <DemoPage />
    </Suspense>
  );
}
