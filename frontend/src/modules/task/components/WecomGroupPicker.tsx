import { useEffect, useState, type Ref } from "react";
import {
  Alert,
  Button,
  EmptyState,
  ErrorState,
  Field,
  FilterBar,
  Pagination,
  Skeleton,
} from "../../../shared/components/ui";
import { formatTime } from "./format";
import { WecomDirectoryStatus } from "./WecomDirectoryStatus";
import type {
  WecomGroup,
  WecomGroupPage,
  SupplierGroupMatchQuery,
  SupplierOption,
} from "../types/supplier-group";
import "./supplier-group-editor.css";

export function WecomGroupPicker({
  supplier,
  selectedId,
  search: load,
  onChoose,
  disabled,
  inputRef,
}: {
  supplier: SupplierOption;
  selectedId?: string;
  search: (query: SupplierGroupMatchQuery) => Promise<WecomGroupPage>;
  onChoose: (group: WecomGroup) => void;
  disabled: boolean;
  inputRef: Ref<HTMLInputElement>;
}) {
  const [input, setInput] = useState(supplier.supplierName);
  const [query, setQuery] = useState<SupplierGroupMatchQuery | null>(null);
  const [state, setState] = useState<
    | { kind: "idle" }
    | { kind: "loading" }
    | { kind: "error"; message: string }
    | { kind: "ready"; data: WecomGroupPage }
  >({ kind: "idle" });
  useEffect(() => {
    if (!query) return;
    let active = true;
    void load(query).then(
      (data) => {
        if (active) setState({ kind: "ready", data });
      },
      (error: unknown) => {
        if (active)
          setState({ kind: "error", message: error instanceof Error ? error.message : "企微群查询失败" });
      },
    );
    return () => {
      active = false;
    };
  }, [query, load]);
  function search(refresh = false) {
    setState({ kind: "loading" });
    setQuery({ supplierId: supplier.supplierId, keyword: keyword(), page: 1, refresh });
  }
  // 默认名称仍使用服务端的供应商自动匹配；仅修改后的关键词进入手工查找。
  function keyword() {
    return input.trim() === supplier.supplierName.trim() ? "" : input.trim();
  }
  const busy = disabled || state.kind === "loading";
  return (
    <section className="sg-picker" aria-label="匹配企微外部群">
      <div className="sg-picker-heading">
        <h4>查找外部群</h4>
        <p>已带入当前供应商名称，也可输入简称、群名、群主或群 ID 查找。</p>
      </div>
      <FilterBar
        embedded
        onSubmit={() => search()}
        actions={
          <>
            <Button type="submit" variant="primary" disabled={busy}>
              {state.kind === "loading" ? "查找中…" : "查找外部群"}
            </Button>
            {query && (
              <Button disabled={busy} onClick={() => search(true)}>
                重新拉取
              </Button>
            )}
          </>
        }
      >
        <Field label="群名、群主或群 ID" grow>
          <input
            ref={inputRef}
            type="search"
            value={input}
            disabled={busy}
            onChange={(event) => setInput(event.target.value)}
            placeholder={supplier.supplierName}
          />
        </Field>
      </FilterBar>
      {state.kind === "idle" && (
        <EmptyState title="尚未查询外部群" description="点击“查找外部群”获取候选，核对群主后选择。" />
      )}
      {query && keyword() !== query.keyword && (
        <p className="it-help">查询条件已修改，点击查找外部群生效。</p>
      )}
      {state.kind === "loading" && <Skeleton rows={2} label="正在查询外部群，首次拉取可能需要一些时间…" />}
      {state.kind === "error" && (
        <ErrorState
          title="外部群查询失败"
          message={state.message}
          action={
            <Button disabled={busy} onClick={() => search()}>
              重新查询
            </Button>
          }
        />
      )}
      {state.kind === "ready" && query && (
        <>
          <WecomDirectoryStatus data={state.data} />
          <p className="sg-picker-count">
            找到 <strong>{state.data.total}</strong> 个候选群，请核对群主后选择。
          </p>
          {state.data.unavailableCount > 0 && (
            <Alert title="部分群不可用" tone="warning">
              另有 {state.data.unavailableCount}{" "}
              个群已失去访问权限或不可用，未列入结果。找不到目标群时请管理员检查群主可见范围。
            </Alert>
          )}
          {state.data.items.length === 0 ? (
            <EmptyState
              title="没有匹配的外部群"
              description="可输入供应商简称或群主重新查找；仍找不到时，请管理员核对应用可见范围。"
            />
          ) : (
            <ul className="sg-picker-results" aria-label="外部群候选">
              {state.data.items.map((group) => (
                <li key={group.chatId} data-selected={selectedId === group.chatId || undefined}>
                  <div>
                    <strong>{group.groupName}</strong>
                    <small>{group.matchReason}</small>
                    <p>
                      群主：{group.employee}（{group.userid}）· {group.memberCount} 人
                    </p>
                    <details>
                      <summary>查看群详情</summary>
                      <p>
                        创建时间：
                        {group.createdAt ? formatTime(group.createdAt) : "未提供"}
                      </p>
                      <p>群标识：{group.chatId}</p>
                    </details>
                  </div>
                  <Button
                    disabled={disabled}
                    variant={selectedId === group.chatId ? "primary" : "secondary"}
                    aria-pressed={selectedId === group.chatId}
                    onClick={() => onChoose(group)}
                  >
                    {selectedId === group.chatId ? "已选择" : "选择此群"}
                  </Button>
                </li>
              ))}
            </ul>
          )}
          <Pagination
            label="企微群查询分页"
            total={state.data.total}
            page={state.data.page}
            pageCount={state.data.pages}
            pageSize={state.data.pageSize}
            pageSizes={[20]}
            disabled={disabled}
            onPageChange={(page) => {
              setState({ kind: "loading" });
              setQuery({ ...query, page, refresh: false });
            }}
            onPageSizeChange={() => {}}
          />
        </>
      )}
    </section>
  );
}
