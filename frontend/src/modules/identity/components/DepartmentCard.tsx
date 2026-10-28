import { useState } from "react";
import {
  Alert,
  Badge,
  Button,
  Card,
  CardContent,
  CardHeader,
  DataTable,
  EmptyState,
} from "../../../shared/components/ui";
import { saveDepartmentRoles, saveScopes } from "../api";
import type { AccessDepartment, RoleItem } from "../types";
import { RoleDialog } from "./RoleDialog";

/**
 * 同步范围与部门默认角色。勾选的部门及其下级部门的成员会被同步、可以登录；
 * 部门默认角色同样作用于下级部门成员。保存后重新同步才会拉取新范围内的成员。
 */
export function DepartmentCard({
  departments,
  roles,
  lastSyncId,
  onSaved,
}: {
  departments: AccessDepartment[];
  roles: RoleItem[];
  /** 最近一次同步记录编号；保存范围后发生新同步即不再提示“请同步” */
  lastSyncId: number | null;
  onSaved: () => Promise<void>;
}) {
  const initial = departments.filter((item) => item.inScope).map((item) => item.id);
  const [draft, setDraft] = useState<Set<number> | null>(null);
  const [editing, setEditing] = useState<AccessDepartment | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  // 保存范围时的同步记录编号；之后有新同步就不再提示
  const [savedAt, setSavedAt] = useState<number | null | undefined>(undefined);
  const saved = savedAt !== undefined && savedAt === lastSyncId;
  const scope = draft ?? new Set(initial);
  const labels = new Map(roles.map((role) => [role.code, role.label]));

  function toggle(id: number) {
    const next = new Set(scope);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setDraft(next);
    setSavedAt(undefined);
  }

  async function save() {
    setBusy(true);
    setError("");
    try {
      await saveScopes([...scope]);
      setDraft(null);
      setSavedAt(lastSyncId);
      await onSaved();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "同步范围保存失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader
        title="同步范围与部门角色"
        description="勾选的部门及其下级部门成员可以登录；部门默认角色同样作用于下级部门成员"
        actions={
          draft && (
            <>
              <Button disabled={busy} onClick={() => setDraft(null)}>
                放弃修改
              </Button>
              <Button variant="primary" disabled={busy} onClick={() => void save()}>
                {busy ? "保存中…" : "保存同步范围"}
              </Button>
            </>
          )
        }
      />
      {error && (
        <CardContent>
          <Alert tone="danger" title="同步范围未保存">
            {error}
          </Alert>
        </CardContent>
      )}
      {saved && (
        <CardContent>
          <Alert tone="info" title="同步范围已保存">
            请点击“立即同步飞书”拉取新范围内的成员；移出范围的人员会在同步后停用。
          </Alert>
        </CardContent>
      )}
      <CardContent flush>
        {departments.length === 0 ? (
          <EmptyState title="还没有飞书部门" description="先点击“立即同步飞书”读取部门。" />
        ) : (
          <DataTable
            label="飞书部门"
            rowKey={(row) => String(row.id)}
            rows={departments}
            minWidth={760}
            columns={[
              { key: "path", header: "部门", render: (row) => row.path },
              {
                key: "scope",
                header: "同步成员",
                width: "180px",
                render: (row) => (
                  <label className="identity-access-check">
                    <input
                      type="checkbox"
                      checked={scope.has(row.id)}
                      disabled={busy}
                      aria-label={`同步 ${row.path} 的成员`}
                      onChange={() => toggle(row.id)}
                    />
                    {scope.has(row.id) ? "同步" : row.covered && !row.inScope ? "随上级同步" : "不同步"}
                  </label>
                ),
              },
              {
                key: "roles",
                header: "默认角色",
                render: (row) =>
                  row.roles.length ? (
                    <span className="identity-access-roles">
                      {row.roles.map((code) => (
                        <Badge key={code} tone="info">
                          {labels.get(code) ?? code}
                        </Badge>
                      ))}
                    </span>
                  ) : (
                    <span className="identity-access-muted">未设置</span>
                  ),
              },
              {
                key: "action",
                header: "操作",
                width: "110px",
                render: (row) => (
                  <Button
                    size="sm"
                    aria-label={`设置 ${row.path} 的默认角色`}
                    onClick={() => setEditing(row)}
                  >
                    设置角色
                  </Button>
                ),
              },
            ]}
          />
        )}
      </CardContent>
      {editing && (
        <RoleDialog
          title={`设置部门默认角色：${editing.name}`}
          description={`${editing.path} 及其下级部门的成员自动获得这些角色。`}
          roles={roles}
          initial={editing.roles}
          onSave={async (codes) => {
            await saveDepartmentRoles(editing.id, codes);
            await onSaved();
          }}
          onClose={() => setEditing(null)}
        />
      )}
    </Card>
  );
}
