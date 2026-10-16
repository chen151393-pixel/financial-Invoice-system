import { useEffect, useRef, useState } from "react";
import { Button } from "../../../shared/components/Button";
import { Pagination } from "../../../shared/components/Pagination";
import { matchWecomGroups, saveSupplierGroup } from "../api/supplier-group";
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
  return (
    <div className="it-page sg-page">
      <p className="it-help">
        供应商来自已同步子采购订单。可导入外部群表后手动关联，或查询企微群并保存；开票任务按供应商身份使用默认绑定。
      </p>
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
      <form
        key={JSON.stringify(query)}
        className="it-search"
        onSubmit={(event) => {
          event.preventDefault();
          const form = new FormData(event.currentTarget);
          change({
            keyword: String(form.get("keyword") || ""),
            account: String(form.get("account") || ""),
            status: String(form.get("status")) as SupplierProfileQuery["status"],
          });
        }}
      >
        <label className="it-search__keyword">
          供应商 / 外部群 / 群主
          <input
            type="search"
            name="keyword"
            defaultValue={query.keyword}
            placeholder="输入供应商名称、群名或群主"
          />
        </label>
        <label>
          NS 环境
          <input name="account" defaultValue={query.account} placeholder="全部环境" />
        </label>
        <label>
          绑定状态
          <select name="status" defaultValue={query.status}>
            <option value="all">全部供应商</option>
            <option value="unbound">未绑定</option>
            <option value="enabled">已绑定 · 启用</option>
            <option value="disabled">已绑定 · 停用</option>
          </select>
        </label>
        <Button type="submit" variant="primary" disabled={busy}>
          查询
        </Button>
        <Button disabled={busy} onClick={reload}>
          刷新
        </Button>
      </form>
      {state.kind === "loading" && (
        <div className="it-empty" role="status">
          正在读取供应商档案…
        </div>
      )}
      {state.kind === "error" && (
        <div className="it-empty" role="alert">
          <h2>供应商档案暂时无法加载</h2>
          <p>{state.message}</p>
          <Button onClick={reload}>重新加载</Button>
        </div>
      )}
      {state.kind === "ready" && (
        <>
          <div className="sg-row sg-between">
            <p className="it-help">
              当前查询：{query.keyword || "全部关键词"} · 共 {state.data.total} 家供应商
            </p>
            <p className="it-help">{state.data.manage.reason}</p>
          </div>
          {state.data.items.length === 0 ? (
            <div className="it-empty">
              <h2>没有符合条件的供应商</h2>
              <p>可调整查询条件；供应商尚未出现时，请先同步相应子采购订单。</p>
            </div>
          ) : (
            <SupplierProfilesTable
              items={state.data.items}
              disabled={!state.data.manage.allowed || editor !== null}
              onEdit={(item) => {
                trigger.current =
                  document.activeElement instanceof HTMLElement ? document.activeElement : null;
                setFeedback("");
                setEditor(item);
              }}
            />
          )}
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
        </>
      )}
    </div>
  );
}
