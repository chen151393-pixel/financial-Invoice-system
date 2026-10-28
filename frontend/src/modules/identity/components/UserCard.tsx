import { useState } from "react";
import {
  Badge,
  Button,
  Card,
  CardContent,
  CardHeader,
  DataTable,
  EmptyState,
} from "../../../shared/components/ui";
import { saveUserRoles } from "../api";
import { formatTime } from "../format";
import type { AccessUser, RoleItem } from "../types";
import { RoleDialog } from "./RoleDialog";

/** 同步范围内的飞书成员；姓名与部门以飞书为准，这里只能调整个人角色。 */
export function UserCard({
  users,
  roles,
  onSaved,
}: {
  users: AccessUser[];
  roles: RoleItem[];
  onSaved: () => Promise<void>;
}) {
  const [editing, setEditing] = useState<AccessUser | null>(null);
  const labels = new Map(roles.map((role) => [role.code, role.label]));
  const roleText = (codes: string[]) => codes.map((code) => labels.get(code) ?? code).join("、");

  return (
    <Card>
      <CardHeader title="人员" description="生效角色由部门默认角色与个人角色计算，以后端结果为准" />
      <CardContent flush>
        {users.length === 0 ? (
          <EmptyState title="同步范围内暂无成员" description="选择同步范围并保存后，点击“立即同步飞书”。" />
        ) : (
          <DataTable
            label="人员"
            rowKey={(row) => String(row.id)}
            rows={users}
            minWidth={900}
            columns={[
              { key: "name", header: "姓名", width: "120px", render: (row) => row.name },
              {
                key: "departments",
                header: "部门",
                render: (row) => row.departments.join("；") || "—",
              },
              {
                key: "status",
                header: "状态",
                width: "150px",
                render: (row) =>
                  row.active ? (
                    <Badge tone="success">可登录</Badge>
                  ) : (
                    <Badge tone="neutral">不可登录：{row.inactiveReason ?? "已停用"}</Badge>
                  ),
              },
              {
                key: "roles",
                header: "生效角色",
                render: (row) =>
                  row.roles.length ? (
                    roleText(row.roles)
                  ) : (
                    <span className="identity-access-muted">无角色，不能登录</span>
                  ),
              },
              {
                key: "source",
                header: "角色来源",
                width: "170px",
                render: (row) =>
                  row.customRoles
                    ? "只按个人角色"
                    : row.personalRoles.length
                      ? `部门默认＋个人（${roleText(row.personalRoles)}）`
                      : "部门默认",
              },
              {
                key: "login",
                header: "最近登录",
                width: "170px",
                render: (row) => formatTime(row.lastLoginAt),
              },
              {
                key: "action",
                header: "操作",
                width: "110px",
                render: (row) => (
                  <Button size="sm" aria-label={`调整 ${row.name} 的角色`} onClick={() => setEditing(row)}>
                    调整角色
                  </Button>
                ),
              },
            ]}
          />
        )}
      </CardContent>
      {editing && (
        <RoleDialog
          title={`调整角色：${editing.name}`}
          description="保存后立即生效；收回全部角色的人员会被退出登录。"
          roles={roles}
          initial={editing.personalRoles}
          customRoles={editing.customRoles}
          onSave={async (codes, custom) => {
            await saveUserRoles(editing.id, codes, custom);
            await onSaved();
          }}
          onClose={() => setEditing(null)}
        />
      )}
    </Card>
  );
}
