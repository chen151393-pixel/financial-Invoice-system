import { lazy, Suspense } from "react";
import { WorkspacePage } from "./WorkspacePage";

// 演示包仅在/demo加载，正式页面不加载原型数据或样式。
const DemoPage = lazy(() => import("./DemoPage"));
export default function App() {
  return location.pathname === "/demo" ? (
    <Suspense fallback={<p role="status">正在加载演示…</p>}>
      <DemoPage />
    </Suspense>
  ) : (
    <WorkspacePage />
  );
}
