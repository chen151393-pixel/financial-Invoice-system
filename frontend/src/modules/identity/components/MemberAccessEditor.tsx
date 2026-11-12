import { useEffect, useRef } from "react";
import {
  Alert,
  Badge,
  Button,
  Card,
  CardContent,
  CardFooter,
  CardHeader,
  EmptyState,
  ErrorState,
  Skeleton,
} from "../../../shared/components/ui";
import { useMemberAccess } from "../hooks/useMemberAccess";
import type { RoleItem } from "../types";

export function MemberAccessEditor({
  id,
  roles,
  onClose,
  onSaved,
  onBusy,
}: {
  id: number;
  roles: RoleItem[];
  onClose: () => void;
  onSaved: () => Promise<void>;
  onBusy: (busy: boolean) => void;
}) {
  const state = useMemberAccess(id, onSaved);
  const heading = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    heading.current?.focus();
  }, [id]);
  useEffect(() => {
    onBusy(state.busy);
    return () => onBusy(false);
  }, [state.busy, onBusy]);
  const { detail, draft, preview, busy } = state;
  const labels = new Map(roles.map((role) => [role.code, role.label]));
  return (
    <Card className="identity-member-editor">
      <CardHeader
        title={
          <span ref={heading} tabIndex={-1}>
            设置成员权限
          </span>
        }
        description={
          detail ? `${detail.name} · ${detail.departments.join(" / ") || "未记录部门"}` : "正在读取成员"
        }
        actions={
          <Button size="sm" disabled={busy} onClick={onClose}>
            关闭
          </Button>
        }
      />
      <CardContent className="identity-member-editor__content">
        {state.loading ? (
          <Skeleton rows={4} label="正在读取成员权限" />
        ) : draft && detail ? (
          <>
            <fieldset disabled={busy}>
              <legend>平台访问</legend>
              <label>
                <input
                  type="checkbox"
                  checked={draft.enabled}
                  onChange={(event) => state.change({ ...draft, enabled: event.target.checked })}
                />
                启用此成员
              </label>
              <p className="identity-access-muted">关闭后无法登录平台</p>
            </fieldset>
            <fieldset disabled={busy}>
              <legend>角色来源</legend>
              <label>
                <input
                  type="radio"
                  name={`source-${id}`}
                  checked={!draft.customRoles}
                  onChange={() => state.change({ ...draft, customRoles: false })}
                />
                继承部门角色，并追加个人角色
              </label>
              <label>
                <input
                  type="radio"
                  name={`source-${id}`}
                  checked={draft.customRoles}
                  onChange={() => state.change({ ...draft, customRoles: true })}
                />
                仅使用个人角色
              </label>
              <div className="identity-role-chips">
                <span>部门默认角色</span>
                {detail.preview.inheritedRoles.map((code) => (
                  <Badge key={code} tone="info">
                    {labels.get(code) ?? code}
                  </Badge>
                ))}
                {!detail.preview.inheritedRoles.length && <span>未设置</span>}
              </div>
            </fieldset>
            <fieldset disabled={busy}>
              <legend>{draft.customRoles ? "个人角色" : "个人追加角色"}</legend>
              <div className="identity-member-editor__roles">
                {roles.map((role) => (
                  <label key={role.code}>
                    <input
                      type="checkbox"
                      checked={draft.roles.includes(role.code)}
                      onChange={() =>
                        state.change({
                          ...draft,
                          roles: draft.roles.includes(role.code)
                            ? draft.roles.filter((code) => code !== role.code)
                            : [...draft.roles, role.code],
                        })
                      }
                    />
                    {role.label}
                  </label>
                ))}
              </div>
              <p className="identity-access-muted">无需重复勾选已继承角色</p>
            </fieldset>
            <section
              aria-label="生效权限预览"
              className="identity-member-editor__preview"
              aria-busy={state.previewing}
            >
              <h3 className="identity-form-title">生效权限预览</h3>
              {state.previewing ? (
                <p role="status">正在读取权限预览…</p>
              ) : preview ? (
                <>
                  <div className="identity-role-chips">
                    {preview.roles.map((code) => (
                      <Badge key={code} tone="info">
                        {labels.get(code) ?? code}
                      </Badge>
                    ))}
                  </div>
                  {preview.pages.length ? (
                    [...new Set(preview.pages.map((page) => page.group))].map((group) => (
                      <div className="identity-role-chips" key={group}>
                        <strong>{group}</strong>
                        {preview.pages
                          .filter((page) => page.group === group)
                          .map((page) => (
                            <Badge key={page.code}>{page.label}</Badge>
                          ))}
                      </div>
                    ))
                  ) : (
                    <EmptyState title="尚无可访问页面" description="请选择角色，或到角色管理中配置页面。" />
                  )}
                  {!preview.canEnable && <Alert tone="warning">{preview.reason}</Alert>}
                  <p className="identity-access-muted">预览随角色选择更新，保存后生效</p>
                </>
              ) : (
                <p className="identity-access-muted">预览不可用，请重新读取成员后再保存。</p>
              )}
            </section>
          </>
        ) : null}
        {state.error && (
          <ErrorState
            title={state.saved ? "已保存，刷新未完成" : "操作未完成"}
            message={state.error}
            action={
              <Button disabled={busy} onClick={() => void state.reload()}>
                重新读取成员
              </Button>
            }
          />
        )}
        {state.saved && <p role="status">成员角色与状态已保存</p>}
      </CardContent>
      <CardFooter className="identity-access-actions">
        <span className="identity-access-muted">页面内操作仍按业务权限校验</span>
        <Button disabled={busy} onClick={onClose}>
          取消
        </Button>
        <Button
          variant="primary"
          disabled={
            busy ||
            state.loading ||
            state.previewing ||
            !preview ||
            (draft?.enabled === true && !preview.canEnable)
          }
          onClick={() => void state.save()}
        >
          {busy ? "保存中…" : "保存角色与状态"}
        </Button>
      </CardFooter>
    </Card>
  );
}
