import { lazy, Suspense } from "react";

// 演示包仅在/demo加载，正式页面不加载原型数据或样式。
const DemoPage = lazy(() => import("./DemoPage"));
const PlWorkspacePage = lazy(() => import("./PlWorkspacePage"));
export default function App() {
  const isPlPage = location.pathname !== "/demo" || new URLSearchParams(location.search).get("view") === "pl";
  if (isPlPage)
    return (
      <Suspense fallback={<p role="status">正在加载 PL 核对…</p>}>
        <PlWorkspacePage />
      </Suspense>
    );
  return (
    <Suspense fallback={<p role="status">正在加载演示…</p>}>
      <DemoPage />
    </Suspense>
  );
}
