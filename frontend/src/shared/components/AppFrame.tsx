import type { ReactNode } from "react";
import { Sidebar, type SidebarGroup } from "./Sidebar";
import "./app-frame.css";

/**
 * 页面外壳：每页只保留一个页头（二级页面可带面包屑），不再叠加顶栏、说明和提示条。
 * 会话操作放在侧栏底部，由应用装配层注入。
 */
export function AppFrame<Id extends string>({
  groups,
  activeId,
  onNavigate,
  title,
  breadcrumb,
  actions,
  children,
  sessionActions,
}: {
  groups: readonly SidebarGroup<Id>[];
  activeId: Id;
  onNavigate: (id: Id) => void;
  title: string;
  breadcrumb?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  sessionActions?: ReactNode;
}) {
  return (
    <div className="platform-frame app-shell">
      <Sidebar
        groups={groups}
        activeId={activeId}
        onNavigate={onNavigate}
        brand={{ mark: "N", title: "发票对账平台", subtitle: "NETSUITE FINANCE HUB" }}
        footer={sessionActions}
      />
      <main className="platform-frame__main">
        <div className="platform-frame__content">
          <header className="platform-frame__heading">
            <div>
              {breadcrumb && (
                <nav className="platform-frame__crumb" aria-label="当前位置">
                  {breadcrumb}
                </nav>
              )}
              <h1>{title}</h1>
            </div>
            {actions}
          </header>
          {children}
        </div>
      </main>
    </div>
  );
}
