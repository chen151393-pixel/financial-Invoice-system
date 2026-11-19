import {
  createContext,
  useContext,
  useId,
  useState,
  type Dispatch,
  type ReactNode,
  type SetStateAction,
} from "react";
import "./sidebar.css";

/** 菜单项下的子页面；short 为窄屏只显示图标时的两三字简称。 */
export interface SidebarChild {
  id: string;
  label: string;
  short?: string;
}

export interface SidebarGroup<Id extends string> {
  label: string;
  items: readonly {
    id: Id;
    label: string;
    icon: ReactNode;
    badge?: string;
    children?: readonly SidebarChild[];
  }[];
}

interface SidebarProps<Id extends string> {
  groups: readonly SidebarGroup<Id>[];
  activeId: Id;
  onNavigate: (id: Id) => void;
  /** 当前子页面；未传 onNavigateChild 时不展示子列表 */
  activeChildId?: string;
  onNavigateChild?: (id: string) => void;
  brand: { mark: string; title: string; subtitle: string };
  footer?: ReactNode;
}

const SidebarExpansion = createContext<[string | null, Dispatch<SetStateAction<string | null>>] | null>(null);

/** 在同一次工作区会话中保留展开状态，切换路由时侧栏可以重新挂载。 */
export function SidebarExpansionProvider({ children }: { children: ReactNode }) {
  const expansion = useState<string | null>(null);
  return <SidebarExpansion value={expansion}>{children}</SidebarExpansion>;
}

/** 公共导航只展示调用方传入的菜单、选中项和状态，不推断业务权限。 */
export function Sidebar<Id extends string>({
  groups,
  activeId,
  onNavigate,
  activeChildId,
  onNavigateChild,
  brand,
  footer,
}: SidebarProps<Id>) {
  const sharedExpansion = useContext(SidebarExpansion);
  const localExpansion = useState<string | null>(null);
  const [expandedItem, setExpandedItem] = sharedExpansion ?? localExpansion;
  const sidebarId = useId();

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
            {group.items.map((item) => {
              const active = activeId === item.id;
              const children = onNavigateChild ? (item.children ?? []) : [];
              const hasChildren = children.length > 0;
              const expanded = hasChildren && expandedItem === item.id;
              const childrenId = hasChildren ? `${sidebarId}-${item.id}` : undefined;
              const current = active
                ? hasChildren
                  ? expanded
                    ? undefined
                    : "location"
                  : "page"
                : undefined;
              return (
                <div key={item.id}>
                  <button
                    type="button"
                    className="app-sidebar__item"
                    aria-current={current}
                    aria-expanded={hasChildren ? expanded : undefined}
                    aria-controls={childrenId}
                    data-active-group={active && hasChildren ? "" : undefined}
                    aria-label={item.badge ? `${item.label}，${item.badge} 项` : item.label}
                    title={item.label}
                    onClick={() => {
                      if (hasChildren) {
                        setExpandedItem((currentItem) => (currentItem === item.id ? null : item.id));
                      } else {
                        onNavigate(item.id);
                      }
                    }}
                  >
                    <span className="app-sidebar__icon" aria-hidden="true">
                      {item.icon}
                    </span>
                    <span className="app-sidebar__item-text">{item.label}</span>
                    {item.badge && <span className="app-sidebar__badge">{item.badge}</span>}
                    {hasChildren && (
                      <svg className="app-sidebar__chevron" viewBox="0 0 16 16" aria-hidden="true">
                        <path
                          d="m6 4 4 4-4 4"
                          fill="none"
                          stroke="currentColor"
                          strokeWidth="1.5"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                        />
                      </svg>
                    )}
                  </button>
                  {hasChildren && (
                    <div
                      id={childrenId}
                      className="app-sidebar__children"
                      role="group"
                      aria-label={`${item.label}子页面`}
                      hidden={!expanded}
                    >
                      {children.map((child) => (
                        <button
                          type="button"
                          className="app-sidebar__child"
                          key={child.id}
                          aria-current={active && child.id === activeChildId ? "page" : undefined}
                          aria-label={child.label}
                          title={child.label}
                          onClick={() => onNavigateChild?.(child.id)}
                        >
                          <span className="app-sidebar__child-text">{child.label}</span>
                          <span className="app-sidebar__child-short" aria-hidden="true">
                            {child.short ?? child.label.slice(0, 2)}
                          </span>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        ))}
      </nav>
      {footer && <div className="app-sidebar__footer">{footer}</div>}
    </aside>
  );
}
