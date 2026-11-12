import { useState } from "react";
import {
  Badge,
  Button,
  Card,
  CardContent,
  CardHeader,
  EmptyState,
  ErrorState,
  Icon,
  Skeleton,
} from "../../../shared/components/ui";
import { AccessTabs } from "../components/AccessTabs";
import { RolePageForm } from "../components/RolePageForm";
import { useRolePages } from "../hooks/useRolePages";
import "./access.css";
import "./role-pages.css";

export function RolePagesPage() {
  const { data, error, loading, reload, save, generation } = useRolePages();
  const [selected, setSelected] = useState("purchaser");
  const [busy, setBusy] = useState(false);
  const role = data?.roles.find((item) => item.code === selected) ?? data?.roles[0];
  return (
    <div className="identity-access-page identity-permissions">
      <AccessTabs value="roles" />
      {error && (
        <ErrorState
          title="角色权限读取失败"
          message={error}
          action={
            <Button disabled={busy} onClick={() => void reload()}>
              重新读取
            </Button>
          }
        />
      )}
      {!data ? (
        loading && <Skeleton rows={6} label="正在读取角色页面权限" />
      ) : (
        <div className="identity-role-layout" aria-busy={loading}>
          <Card>
            <CardHeader title="角色列表" />
            <CardContent className="identity-role-list">
              {data.roles.map((item) => (
                <Button
                  key={item.code}
                  disabled={busy || loading}
                  aria-pressed={role?.code === item.code}
                  onClick={() => setSelected(item.code)}
                >
                  <Icon name="users" />
                  <span>{item.label}</span>
                  {!item.editable && <Badge>内置</Badge>}
                </Button>
              ))}
              <p className="identity-access-muted">选择角色后配置页面权限</p>
            </CardContent>
          </Card>
          {role ? (
            <RolePageForm
              key={`${role.code}:${generation}`}
              role={role}
              pages={data.pages}
              onSave={save}
              onReload={reload}
              onBusy={setBusy}
            />
          ) : (
            <EmptyState title="暂无可配置角色" />
          )}
        </div>
      )}
    </div>
  );
}
