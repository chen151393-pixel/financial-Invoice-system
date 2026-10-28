import { Alert, Card, CardContent } from "../../../shared/components/ui";
import type { AccessOverview } from "../types";
import { DepartmentTree } from "./DepartmentTree";
import { UserCard } from "./UserCard";

/** 首屏与同步完成后只读取已入库的组织及账号，不触发飞书接口。 */
export function ImportedDirectory({
  data,
  department,
  onSelect,
  onSaved,
}: {
  data: AccessOverview;
  department: string;
  onSelect: (id: string) => void;
  onSaved: () => Promise<void>;
}) {
  const departments = data.importedDepartments ?? data.departments;
  const current = departments.find((item) => item.openDepartmentId === department);
  const items = [
    { id: "", name: "全部已导入员工", path: "全部已导入员工", depth: 0 },
    ...departments.map((item) => ({
      id: item.openDepartmentId,
      name: item.name,
      path: item.path,
      depth: item.path.split(" / ").length - 1,
    })),
  ];
  return (
    <Card>
      {data.importedDepartments === undefined && (
        <CardContent>
          <Alert tone="warning">
            后端版本尚未更新，暂显示已保存的部门。点击部门可查看对应员工；隐藏空部门将在后端更新后生效。
          </Alert>
        </CardContent>
      )}
      <div className="identity-directory-layout">
        <DepartmentTree
          items={items}
          selected={current?.openDepartmentId ?? ""}
          description={
            data.importedDepartments === undefined
              ? "已保存部门 · 点击查看对应员工"
              : "仅显示有已导入员工的部门（含下级）"
          }
          onSelect={onSelect}
        />
        <section className="identity-directory-members" aria-label="已导入员工">
          <UserCard
            key={current?.id ?? "all"}
            departments={departments}
            roles={data.roles}
            selectedDepartment={current}
            onSaved={onSaved}
            embedded
          />
        </section>
      </div>
    </Card>
  );
}
