import { Button } from "../../../shared/components/ui";

/** 本地部门与飞书预览共用导航；成员数量只在接口提供时显示。 */
export function DepartmentTree({
  items,
  selected,
  disabled,
  description,
  onSelect,
}: {
  items: { id: string; name: string; path: string; depth: number; memberCount?: number }[];
  selected: string;
  disabled?: boolean;
  description: string;
  onSelect: (id: string) => void;
}) {
  return (
    <aside className="identity-directory-tree" aria-label="部门导航">
      <h3>组织架构</h3>
      <p className="identity-access-muted">{description}</p>
      <div className="identity-directory-branches">
        {items.map((item) => (
          <div key={item.id} style={{ paddingInlineStart: `${Math.min(item.depth, 5) * 12}px` }}>
            <Button
              variant={item.id === selected ? "primary" : "ghost"}
              aria-pressed={item.id === selected}
              disabled={disabled}
              onClick={() => onSelect(item.id)}
              title={item.path}
            >
              <span>{item.name}</span>
              {item.memberCount !== undefined && <span>{item.memberCount}</span>}
            </Button>
          </div>
        ))}
      </div>
    </aside>
  );
}
