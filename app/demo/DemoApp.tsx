"use client";
import { useState, useSyncExternalStore } from "react";
import { AppFrame } from "../../web/shared/components/AppFrame";
import { navigation } from "../../web/app/navigation";
import { workspaceRoutes } from "../../web/app/views";
import { viewMeta } from "./fixtures";
import type { View } from "./types";
import { Dashboard } from "./pages/Dashboard";
import { MatchDetail } from "./pages/MatchDetail";
import { Exceptions } from "./pages/Exceptions";
import { ReconcileCenter } from "./pages/ReconcileCenter";
import { WritebackCenter } from "./pages/WritebackCenter";

function readView(): View {
  const value = new URLSearchParams(window.location.search).get("view");
  return value && Object.hasOwn(viewMeta, value) ? (value as View) : "dashboard";
}

function subscribeNavigation(onChange: () => void) {
  window.addEventListener("popstate", onChange);
  return () => window.removeEventListener("popstate", onChange);
}

export default function Home() {
  const view = useSyncExternalStore(subscribeNavigation, readView, (): View => "dashboard");
  const [toast, setToast] = useState("");
  const notify = (message: string) => {
    setToast(message);
    window.setTimeout(() => setToast(""), 2600);
  };
  const meta = viewMeta[view];
  const navigate = (target: View) => {
    const workspace = workspaceRoutes[target];
    if (workspace) {
      window.location.assign(workspace);
      return;
    }
    const url = new URL(window.location.href);
    url.searchParams.set("view", target);
    window.history.pushState(null, "", url);
    window.dispatchEvent(new PopStateEvent("popstate"));
    window.scrollTo({ top: 0, behavior: "instant" });
  };
  return (
    <AppFrame
      groups={navigation}
      activeId={view}
      onNavigate={navigate}
      title={meta.title}
      subtitle={meta.subtitle}
      mode="demo"
      actions={
        <div className="page-actions">
          <button className="button secondary" onClick={() => navigate("sync")}>
            ⟳ 查看同步状态
          </button>
          <button className="button primary" onClick={() => notify("演示：双数据源增量同步已启动")}>
            ↻ 同步最新数据
          </button>
        </div>
      }
    >
      {view === "pl" && <a href="/pl-reconciliation">进入真实 PL 采购报关核对</a>}
      {view === "finance" && <a href="/finance-reconciliation">进入财务核对</a>}
      {view === "dashboard" && <Dashboard navigate={navigate} />}{" "}
      {view === "invoices" && <a href="/invoices">进入真实进项发票列表</a>}{" "}
      {view === "match" && (
        <MatchDetail notify={notify} back={() => navigate("invoices")} navigate={navigate} />
      )}{" "}
      {view === "exceptions" && <Exceptions notify={notify} />}{" "}
      {view === "sync" && <a href="/sync">进入数据同步中心</a>}{" "}
      {view === "reconcile" && <ReconcileCenter navigate={navigate} />}{" "}
      {view === "writeback" && <WritebackCenter notify={notify} />}
      {toast && (
        <div className="toast" role="status">
          <span>✓</span>
          {toast}
        </div>
      )}
    </AppFrame>
  );
}
