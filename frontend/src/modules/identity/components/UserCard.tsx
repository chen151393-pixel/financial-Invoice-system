import { Fragment, useState } from "react";
import {
  Badge,
  Button,
  Card,
  CardContent,
  CardHeader,
  DataTable,
  EmptyState,
  ErrorState,
  Field,
  FilterBar,
  Pagination,
  Skeleton,
} from "../../../shared/components/ui";
import { useAccessUsers } from "../hooks/useAccessUsers";
import { formatTime } from "../format";
import type { AccessDepartment, AccessUser, RoleItem } from "../types";
import { RoleDialog } from "./RoleDialog";

/** 已导入成员的角色和启用管理；列表筛选、登录资格均由后端返回。 */
export function UserCard({
  departments,
  roles,
  onSaved,
  selectedDepartment,
  embedded = false,
}: {
  departments: AccessDepartment[];
  roles: RoleItem[];
  onSaved: () => Promise<void>;
  selectedDepartment?: AccessDepartment;
  embedded?: boolean;
}) {
  const list = useAccessUsers(onSaved, embedded ? (selectedDepartment?.id ?? null) : selectedDepartment?.id);
  const [editing, setEditing] = useState<AccessUser | null>(null);
  const [editingDepartment, setEditingDepartment] = useState<AccessDepartment | null>(null);
  const labels = new Map(roles.map((role) => [role.code, role.label]));
  const current = departments.find((d) => String(d.id) === list.department);
  const Surface = embedded ? Fragment : Card;
  return (
    <Surface>
      <CardHeader
        title={selectedDepartment ? `${selectedDepartment.name} · 已导入员工` : "全部已导入员工"}
        description="配置部门默认角色或个人角色，并单独控制人员是否启用。"
        actions={current && <Button onClick={() => setEditingDepartment(current)}>设置部门默认角色</Button>}
      />
      <FilterBar
        embedded
        onSubmit={(form) => {
          const data = new FormData(form);
          list.filter(String(data.get("query") ?? ""), String(data.get("department") ?? ""));
        }}
        actions={
          <Button type="submit" disabled={list.loading}>
            查询
          </Button>
        }
      >
        <Field label="姓名" grow>
          <input key={list.query} name="query" defaultValue={list.query} placeholder="搜索已导入成员" />
        </Field>
        {!selectedDepartment && !embedded && (
          <Field label="部门">
            <select name="department" defaultValue={list.department}>
              <option value="">全部部门</option>
              {departments.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.path}
                </option>
              ))}
            </select>
          </Field>
        )}
      </FilterBar>
      <CardContent flush>
        {list.loading ? (
          <Skeleton rows={5} label="正在读取成员权限" />
        ) : list.error ? (
          <ErrorState
            title="成员读取失败"
            message={list.error}
            action={<Button onClick={() => void list.reload()}>重新读取</Button>}
          />
        ) : !list.data?.items.length ? (
          <EmptyState
            title="当前条件下没有成员"
            description="在上方选择部门或人员并确认同步，再设置角色与启用状态；也可调整查询条件。"
          />
        ) : (
          <DataTable
            label="平台成员权限"
            rowKey={(row) => String(row.id)}
            rows={list.data.items}
            minWidth={880}
            columns={[
              {
                key: "name",
                header: "成员",
                render: (row) => (
                  <div className="identity-member-name">
                    <span className="identity-member-avatar" aria-hidden="true">
                      {row.name.slice(0, 1)}
                    </span>
                    <strong>{row.name}</strong>
                  </div>
                ),
              },
              { key: "departments", header: "部门", render: (row) => row.departments.join("；") || "—" },
              {
                key: "roles",
                header: "生效角色",
                render: (row) => row.roles.map((code) => labels.get(code) ?? code).join("、") || "未分配",
              },
              {
                key: "source",
                header: "角色来源",
                render: (row) => (row.customRoles ? "仅个人角色" : "部门默认＋个人"),
              },
              {
                key: "status",
                header: "平台状态",
                render: (row) => (
                  <Badge tone={row.active ? "success" : "neutral"}>
                    {row.active ? "已启用 · 可登录" : (row.inactiveReason ?? "不可登录")}
                  </Badge>
                ),
              },
              { key: "login", header: "最近登录", render: (row) => formatTime(row.lastLoginAt) },
              {
                key: "action",
                header: "操作",
                render: (row) => (
                  <Button
                    size="sm"
                    aria-label={`设置 ${row.name} 的角色与启用状态`}
                    onClick={() => setEditing(row)}
                  >
                    设置权限
                  </Button>
                ),
              },
            ]}
          />
        )}
        {list.data && list.data.total > 50 && (
          <Pagination
            label="平台成员分页"
            {...list.data}
            pageSizes={[50]}
            disabled={list.loading}
            onPageChange={(page) => list.filter(list.query, list.department, page)}
            onPageSizeChange={() => {}}
          />
        )}
      </CardContent>
      {editing && (
        <RoleDialog
          title={`设置权限：${editing.name}`}
          description="保存后立即生效。部门默认角色可继承，个人角色可追加或覆盖。"
          roles={roles}
          initial={editing.personalRoles}
          customRoles={editing.customRoles}
          enabled={editing.enabled}
          onSave={(codes, custom, enabled) => list.saveUser(editing.id, codes, custom, enabled)}
          onClose={() => setEditing(null)}
        />
      )}
      {editingDepartment && (
        <RoleDialog
          title={`部门默认角色：${editingDepartment.name}`}
          description="本部门及下级部门成员继承；只按个人角色的成员不受影响。分配默认角色不会自动启用新成员。"
          roles={roles}
          initial={editingDepartment.roles}
          onSave={(codes) => list.saveDepartment(editingDepartment.id, codes)}
          onClose={() => setEditingDepartment(null)}
        />
      )}
    </Surface>
  );
}
