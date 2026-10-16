import { useEffect, useState, type Ref } from "react";
import { Button } from "../../../shared/components/Button";
import { Pagination } from "../../../shared/components/Pagination";
import { formatTime } from "./format";
import type {
  WecomGroup,
  WecomGroupPage,
  SupplierGroupMatchQuery,
  SupplierOption,
} from "../types/supplier-group";

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
  const [input, setInput] = useState("");
  const [query, setQuery] = useState<SupplierGroupMatchQuery>({
    supplierId: supplier.supplierId,
    keyword: "",
    page: 1,
    refresh: false,
  });
  const [state, setState] = useState<
    { kind: "loading" } | { kind: "error"; message: string } | { kind: "ready"; data: WecomGroupPage }
  >({ kind: "loading" });
  useEffect(() => {
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
    setQuery({ supplierId: supplier.supplierId, keyword: input, page: 1, refresh });
  }
  const busy = disabled || state.kind === "loading";
  return (
    <section className="sg-lookup" aria-label="匹配企微外部群">
      <h3>匹配外部群与群主</h3>
      <p className="it-help">
        按“{supplier.supplierName}”推荐候选群；名称相似不代表同一供应商，请核对后选择。
      </p>
      <form
        className="sg-row"
        onSubmit={(event) => {
          event.preventDefault();
          search();
        }}
      >
        <label>
          群名、群主或群 ID（可选）
          <input
            ref={inputRef}
            type="search"
            value={input}
            disabled={busy}
            onChange={(event) => setInput(event.target.value)}
            placeholder="留空按供应商名称匹配，或输入简称查找"
          />
        </label>
        <Button type="submit" disabled={busy}>
          查找外部群
        </Button>
        <Button disabled={busy} onClick={() => search(true)}>
          重新拉取
        </Button>
      </form>
      {query && input !== query.keyword && <p className="it-help">群名已修改，点击查询生效。</p>}
      {state.kind === "loading" && <p role="status">正在从企微查询客户群，首次拉取可能需要一些时间…</p>}
      {state.kind === "error" && (
        <p role="alert" className="sg-feedback">
          {state.message}{" "}
          <Button disabled={busy} onClick={() => search()}>
            重新查询
          </Button>
        </p>
      )}
      {state.kind === "ready" && (
        <>
          <p className="it-help">
            查询“{query.keyword || supplier.supplierName}”：共 {state.data.total}{" "}
            个候选群。重名时请核对群主、人数及创建时间，系统不会自动绑定。
          </p>
          {state.data.unavailableCount > 0 && (
            <p className="sg-feedback" role="status">
              另有 {state.data.unavailableCount}{" "}
              个群已失去访问权限或不可用，未列入结果。找不到目标群时请管理员检查群主可见范围。
            </p>
          )}
          {state.data.items.length === 0 ? (
            <p>
              没有匹配的外部群。可输入供应商简称、群名或群主重新查找；仍找不到时，请管理员核对应用可见范围。
            </p>
          ) : (
            <ul className="sg-options">
              {state.data.items.map((group) => (
                <li key={group.chatId}>
                  <span>
                    <strong>{group.groupName}</strong>
                    <small>{group.matchReason}</small>
                    <small>
                      群主：{group.employee}（{group.userid}）· {group.memberCount} 人
                    </small>
                    <small>
                      创建时间：
                      {group.createdAt ? formatTime(group.createdAt) : "未提供"}
                    </small>
                    <small>群标识：{group.chatId}</small>
                  </span>
                  <Button
                    disabled={disabled}
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
              setQuery((previous) => ({ ...previous, page, refresh: false }));
            }}
            onPageSizeChange={() => {}}
          />
        </>
      )}
    </section>
  );
}
