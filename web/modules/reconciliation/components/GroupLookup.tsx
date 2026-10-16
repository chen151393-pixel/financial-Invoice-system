import { useEffect, useState, type ReactNode } from "react";
import { Button } from "../../../shared/components/Button";
import { Pagination } from "../../../shared/components/Pagination";
import type { GroupPage } from "../group-api";

export function GroupLookup<T>({
  label,
  load,
  render,
  onChoose,
  disabled = false,
}: {
  label: string;
  load: (keyword: string, page: number) => Promise<GroupPage<T>>;
  render: (item: T) => ReactNode;
  onChoose: (item: T) => void;
  disabled?: boolean;
}) {
  const [input, setInput] = useState("");
  const [query, setQuery] = useState({ keyword: "", page: 1, refresh: 0 });
  const [state, setState] = useState<
    { kind: "loading" } | { kind: "error"; message: string } | { kind: "ready"; data: GroupPage<T> }
  >({ kind: "loading" });
  useEffect(() => {
    let active = true;
    void load(query.keyword, query.page).then(
      (data) => {
        if (active) setState({ kind: "ready", data });
      },
      (error: unknown) => {
        if (active) setState({ kind: "error", message: error instanceof Error ? error.message : "查询失败" });
      },
    );
    return () => {
      active = false;
    };
  }, [query, load]);
  function change(page = 1) {
    setState({ kind: "loading" });
    setQuery((current) => ({ keyword: input, page, refresh: current.refresh + 1 }));
  }
  return (
    <section className="sg-lookup" aria-label={label}>
      <form
        className="sg-row"
        onSubmit={(event) => {
          event.preventDefault();
          change();
        }}
      >
        <label>
          {label}
          <input
            type="search"
            value={input}
            disabled={disabled}
            onChange={(event) => setInput(event.target.value)}
            placeholder="输入名称或 ID"
          />
        </label>
        <Button type="submit" disabled={disabled || state.kind === "loading"}>
          查询
        </Button>
      </form>
      {input !== query.keyword && <p className="it-help">条件已修改，点击查询生效。</p>}
      {state.kind === "loading" && <p role="status">正在查询…</p>}
      {state.kind === "error" && (
        <p role="alert">
          {state.message} <Button onClick={() => change()}>重新查询</Button>
        </p>
      )}
      {state.kind === "ready" && (
        <>
          {state.data.items.length === 0 ? (
            <p>没有符合条件的供应商，请调整关键词或先同步采购来源。</p>
          ) : (
            <ul className="sg-options">
              {state.data.items.map((item, index) => (
                <li key={index}>
                  <span>{render(item)}</span>
                  <Button disabled={disabled} onClick={() => onChoose(item)}>
                    选择
                  </Button>
                </li>
              ))}
            </ul>
          )}
          <Pagination
            label={label + "分页"}
            total={state.data.total}
            page={state.data.page}
            pageCount={state.data.pages}
            pageSize={state.data.pageSize}
            pageSizes={[20]}
            disabled={disabled}
            onPageChange={(page) => {
              setState({ kind: "loading" });
              setQuery((current) => ({ ...current, page }));
            }}
            onPageSizeChange={() => {}}
          />
        </>
      )}
    </section>
  );
}
