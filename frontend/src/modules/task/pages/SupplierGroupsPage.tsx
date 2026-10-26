import { useEffect, useRef, useState } from "react";
import {
  Button,
  Card,
  CardFooter,
  EmptyState,
  ErrorState,
  Field,
  FilterBar,
  Pagination,
  SectionTitle,
  Skeleton,
} from "../../../shared/components/ui";
import { matchWecomGroups, saveSupplierGroup, saveSupplierNotify } from "../api/supplier-group";
import { SupplierGroupEditor } from "../components/SupplierGroupEditor";
import { SupplierProfilesTable } from "../components/SupplierProfilesTable";
import { useSupplierProfiles } from "../hooks/useSupplierProfiles";
import type { SupplierProfile, SupplierProfileQuery } from "../types/supplier-group";
import "./task.css";
import "./supplier-groups.css";

export function SupplierGroupsPage() {
  const { query, state, change, reload } = useSupplierProfiles();
  const [editor, setEditor] = useState<SupplierProfile | null>(null);
  const [feedback, setFeedback] = useState("");
  const [saving, setSaving] = useState<string | null>(null);
  const trigger = useRef<HTMLElement | null>(null);
  const feedbackElement = useRef<HTMLParagraphElement>(null);
  const restoreFocus = useRef(false);
  const busy = state.kind === "loading";
  useEffect(() => {
    if (editor || !restoreFocus.current) return;
    restoreFocus.current = false;
    if (feedback) feedbackElement.current?.focus();
    else trigger.current?.focus();
  }, [editor, feedback]);
  function close() {
    restoreFocus.current = true;
    setEditor(null);
  }
  async function notify(item: SupplierProfile, enabled: boolean) {
    setSaving(item.supplierId);
    setFeedback("");
    try {
      await saveSupplierNotify(item.supplierId, enabled, item.notify.revision);
      setFeedback(
        enabled
          ? `已开启 ${item.supplierName} 的供应商通知，之后审核通过将照常生成开票任务。`
          : `已关闭 ${item.supplierName} 的供应商通知，之后审核通过不再生成该供应商的开票任务；已有任务不变。`,
      );
    } catch (error) {
      setFeedback(error instanceof Error ? error.message : "供应商通知设置保存失败，请刷新后重试");
    } finally {
      setSaving(null);
      reload();
    }
  }
  return (
    <div className="it-page sg-page">
      {feedback && (
        <p ref={feedbackElement} tabIndex={-1} role="status" className="sg-feedback">
          {feedback}
        </p>
      )}
      {editor && (
        <SupplierGroupEditor
          key={editor.supplierId}
          initial={editor}
          searchWecom={matchWecomGroups}
          save={saveSupplierGroup}
          onClose={close}
          onSaved={() => {
            close();
            setFeedback("供应商档案已保存。后续新通知将带出启用的默认群，已保存通知保持原内容。");
            reload();
          }}
        />
      )}
      <FilterBar
        key={JSON.stringify(query)}
        onSubmit={(element) => {
          const form = new FormData(element);
          change({
            keyword: String(form.get("keyword") || ""),
            status: String(form.get("status")) as SupplierProfileQuery["status"],
          });
        }}
        actions={
          <>
            <Button type="submit" variant="primary" disabled={busy}>
              查询
            </Button>
            <Button disabled={busy} onClick={reload}>
              刷新
            </Button>
          </>
        }
      >
        <Field label="供应商 / 外部群 / 群主" grow>
          <input
            type="search"
            name="keyword"
            defaultValue={query.keyword}
            placeholder="输入供应商名称、群名或群主"
          />
        </Field>
        <Field label="绑定状态">
          <select name="status" defaultValue={query.status}>
            <option value="all">全部供应商</option>
            <option value="unbound">未绑定</option>
            <option value="enabled">已绑定 · 启用</option>
            <option value="disabled">已绑定 · 停用</option>
          </select>
        </Field>
      </FilterBar>
      <SectionTitle
        title="供应商"
        count={state.kind === "ready" ? `共 ${state.data.total} 家` : undefined}
        actions={
          state.kind === "ready" ? <span className="sg-manage">{state.data.manage.reason}</span> : undefined
        }
      />
      {state.kind === "loading" && <Skeleton label="正在读取供应商档案" />}
      {state.kind === "error" && (
        <Card>
          <ErrorState
            title="供应商档案暂时无法加载"
            message={state.message}
            action={<Button onClick={reload}>重新加载</Button>}
          />
        </Card>
      )}
      {state.kind === "ready" && (
        <Card>
          {state.data.items.length === 0 ? (
            <EmptyState
              title="没有符合条件的供应商"
              description="可调整查询条件；供应商尚未出现时，请先同步相应子采购订单。"
            />
          ) : (
            <SupplierProfilesTable
              items={state.data.items}
              disabled={!state.data.manage.allowed || editor !== null}
              saving={saving}
              onNotify={(item, enabled) => void notify(item, enabled)}
              onEdit={(item) => {
                trigger.current =
                  document.activeElement instanceof HTMLElement ? document.activeElement : null;
                setFeedback("");
                setEditor(item);
              }}
            />
          )}
          <CardFooter>
            <Pagination
              label="供应商档案分页"
              total={state.data.total}
              page={state.data.page}
              pageCount={state.data.pages}
              pageSize={state.data.pageSize}
              pageSizes={[10, 20, 50]}
              onPageChange={(page) => change({ page })}
              onPageSizeChange={(pageSize) => change({ pageSize })}
            />
          </CardFooter>
        </Card>
      )}
      <details className="sg-definitions">
        <summary>使用说明</summary>
        <p>
          供应商来自已同步子采购订单。可导入外部群表后手动关联，或查询企微群并保存；开票任务按供应商身份使用默认绑定。
        </p>
      </details>
    </div>
  );
}
