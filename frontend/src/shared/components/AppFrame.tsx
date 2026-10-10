import type { ReactNode } from "react";
import { Sidebar, type SidebarGroup } from "./Sidebar";
import "./app-frame.css";

export function AppFrame<Id extends string>({
  groups,
  activeId,
  onNavigate,
  title,
  subtitle,
  mode,
  actions,
  children,
  notice,
  dataLabel,
}: {
  groups: readonly SidebarGroup<Id>[];
  activeId: Id;
  onNavigate: (id: Id) => void;
  title: string;
  subtitle: string;
  mode: "live" | "pending";
  actions?: ReactNode;
  children: ReactNode;
  notice?: string | null;
  dataLabel?: string;
}) {
  return (
    <div className="platform-frame app-shell">
      <Sidebar
        groups={groups}
        activeId={activeId}
        onNavigate={onNavigate}
        brand={{ mark: "N", title: "发票对账平台", subtitle: "NETSUITE FINANCE HUB" }}
        footer={
          <>
            <strong>发票对账平台</strong>
            <span>PL 核对与 NS 拉取已接入</span>
          </>
        }
      />
      <main className="platform-frame__main">
        <header className="platform-frame__topbar">
          <span>发票对账平台 / {title}</span>
          <span className="platform-frame__badge">
            {dataLabel ?? (mode === "live" ? "实时数据 · 只读查询" : "数据源接入状态")}
          </span>
        </header>
        <div className="platform-frame__content">
          <div className="platform-frame__heading">
            <div>
              <h1>{title}</h1>
              <p>{subtitle}</p>
            </div>
            {actions}
          </div>
          {notice !== null && (
            <p className="platform-frame__notice">
              {notice ??
                (mode === "live"
                  ? "本页通过后端读取 NS 真实数据，支持核对和导出，不写入 NS。"
                  : "本页显示各数据源的接入状态。")}
            </p>
          )}
          {children}
        </div>
      </main>
    </div>
  );
}
