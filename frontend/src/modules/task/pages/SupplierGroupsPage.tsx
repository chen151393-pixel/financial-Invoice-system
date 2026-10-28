import { useEffect, useRef, useState } from "react";
import {
  Button,
  Card,
  CardFooter,
  CardHeader,
  EmptyState,
  ErrorState,
  Pagination,
  Skeleton,
  StatCard,
  StatGrid,
} from "../../../shared/components/ui";
import { matchWecomGroups, saveSupplierGroup, saveSupplierNotify } from "../api/supplier-group";
import { InvoicingSpeedCard } from "../components/InvoicingSpeedCard";
import { SupplierGroupEditor } from "../components/SupplierGroupEditor";
import { SupplierProfileSearch } from "../components/SupplierProfileSearch";
import { SupplierProfilesTable } from "../components/SupplierProfilesTable";
import { useSupplierProfiles } from "../hooks/useSupplierProfiles";
import type { SupplierProfile, SupplierProfileList } from "../types/supplier-group";
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
  // 最近一次成功结果的概况计数；重新查询时保留，避免闪烁
  const [counts, setCounts] = useState<SupplierProfileList["counts"] | null>(null);
  if (state.kind === "ready" && state.data.counts !== counts) setCounts(state.data.counts);
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
      {counts && (
        <StatGrid label="绑定概况">
          <StatCard glyph="全" label="全部供应商" value={`${counts.all} 家`} note="来自已同步的子采购订单" />
          <StatCard
            glyph="群"
            label="已绑定开票群"
            value={`${counts.bound} 家`}
            note="通知时默认带出绑定的企微群"
          />
          <StatCard
            glyph="未"
            tone={counts.unbound > 0 ? "warning" : "neutral"}
            label="未绑定开票群"
            value={`${counts.unbound} 家`}
            note="可导入外部群表或查询企微群后关联"
          />
          <StatCard
            glyph="关"
            label="已关闭通知"
            value={`${counts.notifyOff} 家`}
            note="审核通过后不生成该供应商的开票任务"
          />
        </StatGrid>
      )}
      {/* 供应商列表与开票时效并排，窄屏上下排列 */}
      <div className="sg-layout">
        <Card className="sg-panel">
          <CardHeader
            title="供应商"
            description={state.kind === "ready" ? `共 ${state.data.total} 家` : undefined}
            actions={
              state.kind === "ready" ? (
                <span className="sg-manage">{state.data.manage.reason}</span>
              ) : undefined
            }
          />
          <SupplierProfileSearch
            key={JSON.stringify(query)}
            query={query}
            busy={busy}
            onSearch={change}
            onRefresh={reload}
          />
          {state.kind === "loading" && <Skeleton label="正在读取供应商档案" />}
          {state.kind === "error" && (
            <ErrorState
              title="供应商档案暂时无法加载"
              message={state.message}
              action={<Button onClick={reload}>重新加载</Button>}
            />
          )}
          {state.kind === "ready" && (
            <>
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
            </>
          )}
        </Card>
        <InvoicingSpeedCard />
      </div>
      <details className="sg-definitions">
        <summary>使用说明</summary>
        <p>
          供应商来自已同步子采购订单。可导入外部群表后手动关联，或查询企微群并保存；开票任务按供应商身份使用默认绑定。
        </p>
      </details>
    </div>
  );
}
