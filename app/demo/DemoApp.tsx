"use client";
import { useState } from "react";
import { viewMeta } from "./fixtures";
import type { View } from "./types";
import { Dashboard } from "./pages/Dashboard";
import { InvoiceList } from "./pages/InvoiceList";
import { MatchDetail } from "./pages/MatchDetail";
import { Exceptions } from "./pages/Exceptions";
import { SyncCenter } from "./pages/SyncCenter";
import { ReconcileCenter } from "./pages/ReconcileCenter";
import { WritebackCenter } from "./pages/WritebackCenter";

export default function Home() {
  const [view, setView] = useState<View>("dashboard");
  const [toast, setToast] = useState("");
  const notify = (message: string) => {
    setToast(message);
    window.setTimeout(() => setToast(""), 2600);
  };
  const meta = viewMeta[view];
  const navigate = (target: View) => {
    setView(target);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">N</div>
          <div>
            <strong>发票对账平台</strong>
            <span>NetSuite Finance Hub</span>
          </div>
        </div>
        <nav className="nav" aria-label="主菜单">
          <p className="nav-label">发票管理</p>
          <button
            className={`nav-item ${view === "dashboard" ? "active" : ""}`}
            onClick={() => navigate("dashboard")}
          >
            <span>▦</span>发票工作台<i>47</i>
          </button>
          <button
            className={`nav-item ${view === "invoices" ? "active" : ""}`}
            onClick={() => navigate("invoices")}
          >
            <span>▤</span>进项发票
          </button>
          <button
            className={`nav-item ${view === "match" ? "active" : ""}`}
            onClick={() => navigate("match")}
          >
            <span>⌁</span>自动匹配
          </button>
          <button
            className={`nav-item ${view === "exceptions" ? "active" : ""}`}
            onClick={() => navigate("exceptions")}
          >
            <span>!</span>异常处理<i>47</i>
          </button>
          <p className="nav-label nav-label-spaced">集成与控制</p>
          <button className={`nav-item ${view === "sync" ? "active" : ""}`} onClick={() => navigate("sync")}>
            <span>↻</span>数据同步
          </button>
          <button
            className={`nav-item ${view === "reconcile" ? "active" : ""}`}
            onClick={() => navigate("reconcile")}
          >
            <span>⇄</span>系统对账
          </button>
          <button
            className={`nav-item ${view === "writeback" ? "active" : ""}`}
            onClick={() => navigate("writeback")}
          >
            <span>↗</span>回写 NetSuite<i>3</i>
          </button>
        </nav>
        <div className="sidebar-foot">
          <div className="dual-dots">
            <i />
            <i />
          </div>
          <div>
            <strong>双数据源连接正常</strong>
            <span>NS 10:26 · 柠檬云 10:28</span>
          </div>
        </div>
      </aside>
      <main className="main">
        <header className="topbar">
          <div className="crumb">
            发票对账平台 <span>/</span> {meta.title}
          </div>
          <div className="top-actions">
            <span className="environment-badge">SANDBOX</span>
            <button className="icon-button" aria-label="搜索">
              ⌕
            </button>
            <button className="icon-button" aria-label="消息">
              ◌
            </button>
            <div className="avatar">陈</div>
            <div className="user">
              <strong>陈静</strong>
              <span>AP 财务经理</span>
            </div>
          </div>
        </header>
        <section className={`content ${view === "exceptions" ? "wide-content" : ""}`}>
          <div className="page-head">
            <div>
              <h1>{meta.title}</h1>
              <p>{meta.subtitle}</p>
            </div>
            <div className="page-actions">
              <button className="button secondary" onClick={() => navigate("sync")}>
                ⟳ 查看同步状态
              </button>
              <button className="button primary" onClick={() => notify("双数据源增量同步已启动")}>
                ↻ 同步最新数据
              </button>
            </div>
          </div>
          {view === "dashboard" && <Dashboard navigate={navigate} />}{" "}
          {view === "invoices" && <InvoiceList navigate={navigate} />}{" "}
          {view === "match" && (
            <MatchDetail notify={notify} back={() => navigate("invoices")} navigate={navigate} />
          )}{" "}
          {view === "exceptions" && <Exceptions notify={notify} />}{" "}
          {view === "sync" && <SyncCenter notify={notify} />}{" "}
          {view === "reconcile" && <ReconcileCenter navigate={navigate} />}{" "}
          {view === "writeback" && <WritebackCenter notify={notify} />}
        </section>
      </main>
      {toast && (
        <div className="toast">
          <span>✓</span>
          {toast}
        </div>
      )}
    </div>
  );
}
