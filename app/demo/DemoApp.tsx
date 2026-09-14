"use client";
import { useState, useSyncExternalStore } from "react";
import { AppFrame } from "../../web/shared/components/AppFrame";
import { navigation } from "../../web/app/navigation";
import { viewMeta } from "./fixtures";
import type { View } from "./types";
import { Dashboard } from "./pages/Dashboard";
import { InvoiceList } from "./pages/InvoiceList";
import { MatchDetail } from "./pages/MatchDetail";
import { Exceptions } from "./pages/Exceptions";
import { SyncCenter } from "./pages/SyncCenter";
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
    if (target === "pl") {
      window.location.assign("/pl-reconciliation");
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
      {view === "dashboard" && <Dashboard navigate={navigate} />}{" "}
      {view === "invoices" && <InvoiceList navigate={navigate} />}{" "}
      {view === "match" && (
        <MatchDetail notify={notify} back={() => navigate("invoices")} navigate={navigate} />
      )}{" "}
      {view === "exceptions" && <Exceptions notify={notify} />}{" "}
      {view === "sync" && <SyncCenter notify={notify} />}{" "}
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
