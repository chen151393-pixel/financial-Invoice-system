import { useEffect, useState, type Ref } from "react";
import { Button } from "../../../shared/components/Button";
import { Pagination } from "../../../shared/components/Pagination";
import { queryWecomGroups, type WecomGroupPage, type WecomGroup } from "../group-api";

export function WecomGroupPicker({
  onChoose,
  disabled,
  inputRef,
}: {
  onChoose: (group: WecomGroup) => void;
  disabled: boolean;
  inputRef: Ref<HTMLInputElement>;
}) {
  const [input, setInput] = useState("");
  const [query, setQuery] = useState<{ keyword: string; page: number; refresh: boolean } | null>(null);
  const [state, setState] = useState<
    | { kind: "idle" | "loading" }
    | { kind: "error"; message: string }
    | { kind: "ready"; data: WecomGroupPage }
  >({ kind: "idle" });
  useEffect(() => {
    if (!query) return;
    let active = true;
    void queryWecomGroups(query).then(
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
  }, [query]);
  function search(refresh = false) {
    setState({ kind: "loading" });
    setQuery({ keyword: input, page: 1, refresh });
  }
  const busy = disabled || state.kind === "loading";
  return (
    <section className="sg-lookup" aria-label="查询企微外部群">
      <form
        className="sg-row"
        onSubmit={(event) => {
          event.preventDefault();
          search();
        }}
      >
        <label>
          企微群名称
          <input
            ref={inputRef}
            type="search"
            value={input}
            disabled={busy}
            onChange={(event) => setInput(event.target.value)}
            placeholder="输入完整群名或部分名称"
          />
        </label>
        <Button type="submit" disabled={busy}>
          查询企微群
        </Button>
        <Button disabled={busy} onClick={() => search(true)}>
          重新拉取
        </Button>
      </form>
      {state.kind === "idle" && (
        <p className="it-help">输入群名后查询，选择正确的群；群 ID 和群主信息由企微自动提供。</p>
      )}
      {query && input !== query.keyword && <p className="it-help">群名已修改，点击查询生效。</p>}
      {state.kind === "loading" && <p role="status">正在从企微查询客户群，首次拉取可能需要一些时间…</p>}
      {state.kind === "error" && (
        <p role="alert" className="sg-feedback">
          {state.message}
        </p>
      )}
      {state.kind === "ready" && (
        <>
          <p className="it-help">
            查询“{query?.keyword}”：共 {state.data.total} 个群。重名时请核对群主、人数及创建时间。
          </p>
          {state.data.unavailableCount > 0 && (
            <p className="sg-feedback" role="status">
              另有 {state.data.unavailableCount}{" "}
              个群已失去访问权限或不可用，未列入结果。找不到目标群时请管理员检查群主可见范围。
            </p>
          )}
          {state.data.items.length === 0 ? (
            <p>没有找到对应的企微群。请核对群名，或联系管理员确认群主在应用可见范围内。</p>
          ) : (
            <ul className="sg-options">
              {state.data.items.map((group) => (
                <li key={group.chatId}>
                  <span>
                    <strong>{group.groupName}</strong>
                    <small>
                      群主：{group.employee} · {group.memberCount} 人
                    </small>
                    <small>
                      创建时间：
                      {group.createdAt
                        ? new Date(group.createdAt).toLocaleString("zh-CN", { timeZone: "Asia/Shanghai" })
                        : "未提供"}
                    </small>
                    <small>群标识：{group.chatId}</small>
                  </span>
                  <Button disabled={disabled} onClick={() => onChoose(group)}>
                    选择此群
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
              setQuery((previous) => (previous ? { ...previous, page, refresh: false } : null));
            }}
            onPageSizeChange={() => {}}
          />
        </>
      )}
    </section>
  );
}
