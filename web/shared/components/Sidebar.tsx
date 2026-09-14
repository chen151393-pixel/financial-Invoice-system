import type { ReactNode } from "react";
import "./sidebar.css";

export interface SidebarGroup<Id extends string> {
  label: string;
  items: readonly { id: Id; label: string; icon: ReactNode; badge?: string }[];
}

interface SidebarProps<Id extends string> {
  groups: readonly SidebarGroup<Id>[];
  activeId: Id;
  onNavigate: (id: Id) => void;
  brand: { mark: string; title: string; subtitle: string };
  footer?: ReactNode;
}

/** 公共导航只展示调用方传入的菜单、选中项和状态，不推断业务权限。 */
export function Sidebar<Id extends string>({
  groups,
  activeId,
  onNavigate,
  brand,
  footer,
}: SidebarProps<Id>) {
  return (
    <aside className="app-sidebar">
      <div className="app-sidebar__brand">
        <div className="app-sidebar__mark" aria-hidden="true">
          {brand.mark}
        </div>
        <div className="app-sidebar__brand-text">
          <strong>{brand.title}</strong>
          <span>{brand.subtitle}</span>
        </div>
      </div>
      <nav className="app-sidebar__nav" aria-label="主菜单">
        {groups.map((group) => (
          <div className="app-sidebar__group" key={group.label}>
            <p className="app-sidebar__label">{group.label}</p>
            {group.items.map((item) => (
              <button
                type="button"
                className="app-sidebar__item"
                key={item.id}
                aria-current={activeId === item.id ? "page" : undefined}
                aria-label={item.badge ? `${item.label}，${item.badge} 项` : item.label}
                title={item.label}
                onClick={() => onNavigate(item.id)}
              >
                <span className="app-sidebar__icon" aria-hidden="true">
                  {item.icon}
                </span>
                <span className="app-sidebar__item-text">{item.label}</span>
                {item.badge && <span className="app-sidebar__badge">{item.badge}</span>}
              </button>
            ))}
          </div>
        ))}
      </nav>
      {footer && <div className="app-sidebar__footer">{footer}</div>}
    </aside>
  );
}
