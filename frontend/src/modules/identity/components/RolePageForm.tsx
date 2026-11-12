import { useRef, useState } from "react";
import {
  Alert,
  Badge,
  Button,
  Card,
  CardContent,
  CardFooter,
  CardHeader,
  DataTable,
} from "../../../shared/components/ui";
import type { PageItem, RolePages } from "../types";

export function RolePageForm({
  role,
  pages,
  onSave,
  onReload,
  onBusy,
}: {
  role: RolePages;
  pages: PageItem[];
  onSave: (role: RolePages, pages: string[]) => Promise<RolePages>;
  onReload: () => Promise<void>;
  onBusy: (busy: boolean) => void;
}) {
  const [selected, setSelected] = useState(role.pages);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  const submitting = useRef(false);
  function toggle(code: string) {
    setSaved(false);
    setSelected((current) =>
      current.includes(code) ? current.filter((item) => item !== code) : [...current, code],
    );
  }
  async function save() {
    if (submitting.current) return;
    submitting.current = true;
    setBusy(true);
    onBusy(true);
    setError("");
    setSaved(false);
    try {
      const result = await onSave(role, selected);
      setSelected(result.pages);
      setSaved(true);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "保存失败");
    } finally {
      submitting.current = false;
      setBusy(false);
      onBusy(false);
    }
  }
  return (
    <Card>
      <CardHeader
        title={
          <>
            {role.label} <Badge tone="info">{role.editable ? "可配置" : "内置"}</Badge>
          </>
        }
        description="配置该角色能够看到和进入的页面"
      />
      <CardContent className="identity-role-content">
        <Alert>
          {role.editable
            ? "多角色权限取并集；页面详情随对应页面授权。"
            : "系统管理员固定拥有全部页面权限，用于维护人员和角色授权。"}
        </Alert>
        <h3 className="identity-form-title">页面访问权限</h3>
        <DataTable
          label={`${role.label}页面权限`}
          rows={pages}
          rowKey={(row) => row.code}
          minWidth={560}
          density="compact"
          columns={[
            { key: "group", header: "分组", width: "16%", render: (row) => row.group },
            { key: "page", header: "页面", width: "24%", render: (row) => row.label },
            {
              key: "allowed",
              header: "允许访问",
              align: "center",
              width: "16%",
              render: (row) => (
                <input
                  type="checkbox"
                  aria-label={`允许访问${row.label}`}
                  checked={selected.includes(row.code)}
                  disabled={busy || !role.editable || !row.assignable}
                  onChange={() => toggle(row.code)}
                />
              ),
            },
            { key: "description", header: "说明", render: (row) => row.description },
          ]}
        />
        <p className="identity-access-muted">
          这里配置页面访问范围，页面内操作权限另行校验。“只读”角色尚不代表所有业务写操作已受限。
        </p>
        {role.editable && !selected.length && (
          <Alert tone="warning">
            此角色没有可访问页面。成员若未获得其他角色授权，将看到暂无页面权限的提示。
          </Alert>
        )}
        {error && (
          <Alert tone="danger" title="权限未保存">
            {error}{" "}
            <Button size="sm" disabled={busy} onClick={() => void onReload()}>
              重新读取配置
            </Button>
          </Alert>
        )}
        {saved && (
          <p className="identity-access-muted" role="status">
            页面权限已保存，将在成员下一次请求时生效。
          </p>
        )}
      </CardContent>
      {role.editable && (
        <CardFooter className="identity-access-actions">
          <span className="identity-access-muted">修改后需保存生效</span>
          <Button
            disabled={busy}
            onClick={() => {
              setSelected(role.pages);
              setError("");
              setSaved(false);
            }}
          >
            取消修改
          </Button>
          <Button variant="primary" disabled={busy} onClick={() => void save()}>
            {busy ? "保存中…" : "保存页面权限"}
          </Button>
        </CardFooter>
      )}
    </Card>
  );
}
