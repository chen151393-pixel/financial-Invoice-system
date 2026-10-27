import type { ReactNode } from "react";
import { Sidebar, type SidebarGroup } from "./Sidebar";
import "./app-frame.css";

/**
 * 页面外壳：固定格式的白色页头（面包屑、标题、一句说明，右侧只放只读信息），
 * 业务按钮一律放在页面内容里，不放在页头。会话操作放在侧栏底部，由应用装配层注入。
 */
export function AppFrame<Id extends string>({
  groups,
  activeId,
  onNavigate,
  title,
  description,
  meta,
  breadcrumb,
  children,
  sessionActions,
}: {
  groups: readonly SidebarGroup<Id>[];
  activeId: Id;
  onNavigate: (id: Id) => void;
  title: string;
  description?: ReactNode;
  /** 只读信息，如数据来源；不得放按钮 */
  meta?: readonly { label: string; value: ReactNode }[];
  breadcrumb?: ReactNode;
  children: ReactNode;
  sessionActions?: ReactNode;
}) {
  return (
    <div className="platform-frame app-shell">
      <Sidebar
        groups={groups}
        activeId={activeId}
        onNavigate={onNavigate}
        brand={{ mark: "N", title: "发票对账平台", subtitle: "FINANCE HUB" }}
        footer={sessionActions}
      />
      <main className="platform-frame__main">
        <header className="platform-frame__header">
          <div className="platform-frame__header-inner">
            <div className="platform-frame__heading">
              {breadcrumb && (
                <nav className="platform-frame__crumb" aria-label="当前位置">
                  {breadcrumb}
                </nav>
              )}
              <h1>{title}</h1>
              {description && <p>{description}</p>}
            </div>
            {meta && meta.length > 0 && (
              <dl className="platform-frame__meta">
                {meta.map((item) => (
                  <div key={item.label}>
                    <dt>{item.label}</dt>
                    <dd>{item.value}</dd>
                  </div>
                ))}
              </dl>
            )}
          </div>
        </header>
        <div className="platform-frame__content">{children}</div>
      </main>
    </div>
  );
}
