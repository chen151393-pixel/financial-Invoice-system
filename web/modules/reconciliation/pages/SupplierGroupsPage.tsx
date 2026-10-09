import { useEffect, useState } from "react";
import { Button } from "../../../shared/components/Button";
import { Pagination } from "../../../shared/components/Pagination";
import { openLocalSession } from "../../identity/api";
import { SupplierGroupEditor } from "../components/SupplierGroupEditor";
import { querySupplierGroups, type GroupBinding, type GroupList, type GroupQuery } from "../group-api";
import "./invoice-task.css";
import "./supplier-groups.css";

export function SupplierGroupsPage() {
  const [query, setQuery] = useState<GroupQuery>({
    keyword: "",
    account: "",
    status: "all",
    page: 1,
    pageSize: 20,
  });
  const [keyword, setKeyword] = useState("");
  const [refresh, setRefresh] = useState(0);
  const [state, setState] = useState<
    { kind: "loading" } | { kind: "error"; message: string } | { kind: "ready"; data: GroupList }
  >({ kind: "loading" });
  const [editor, setEditor] = useState<GroupBinding | null | undefined>(undefined);
  const [feedback, setFeedback] = useState<{ error: boolean; message: string } | null>(null);
  useEffect(() => {
    let active = true;
    async function load() {
      try {
        await openLocalSession();
        const data = await querySupplierGroups(query);
        if (active) setState({ kind: "ready", data });
      } catch (error) {
        if (active)
          setState({ kind: "error", message: error instanceof Error ? error.message : "配置读取失败" });
      }
    }
    void load();
    return () => {
      active = false;
    };
  }, [query, refresh]);
  function change(patch: Partial<GroupQuery>) {
    setState({ kind: "loading" });
    setQuery((previous) => ({ ...previous, page: 1, ...patch }));
  }
  function reload() {
    setState({ kind: "loading" });
    setRefresh((value) => value + 1);
  }
  const busy = state.kind === "loading";
  return (
    <div className="it-page sg-page">
      <p className="it-help">
        选择系统供应商，按名称查询并选择对应的企微群。新通知自动带出默认群；已保存的通知保留原内容。
      </p>
      {feedback && (
        <p role={feedback.error ? "alert" : "status"} className="sg-feedback">
          {feedback.message}
        </p>
      )}
      {state.kind === "ready" && (
        <div className="sg-row sg-between">
          <Button
            variant="primary"
            disabled={!state.data.manage.allowed || editor !== undefined}
            onClick={() => {
              setFeedback(null);
              setEditor(null);
            }}
          >
            新增配置
          </Button>
          <span className="it-help">{state.data.manage.reason}</span>
        </div>
      )}
      {editor !== undefined && (
        <SupplierGroupEditor
          initial={editor}
          onClose={() => setEditor(undefined)}
          onSaved={() => {
            setEditor(undefined);
            setFeedback({ error: false, message: "供应商群配置已保存。新通知将使用启用的默认群。" });
            reload();
          }}
        />
      )}
      <form
        className="it-search"
        onSubmit={(event) => {
          event.preventDefault();
          change({ keyword });
        }}
      >
        <label className="it-search__keyword">
          供应商 / 企微群 / 群主
          <input
            type="search"
            value={keyword}
            onChange={(event) => setKeyword(event.target.value)}
            placeholder="输入名称或 ID"
          />
        </label>
        <label>
          配置状态
          <select
            value={query.status}
            disabled={busy}
            onChange={(event) => change({ status: event.target.value as GroupQuery["status"] })}
          >
            <option value="all">全部状态</option>
            <option value="enabled">启用</option>
            <option value="disabled">停用</option>
          </select>
        </label>
        <Button type="submit" disabled={busy}>
          查询
        </Button>
        <Button disabled={busy} onClick={reload}>
          刷新
        </Button>
      </form>
      {keyword !== query.keyword && <p className="it-help">查询条件已修改，点击查询生效。</p>}
      {state.kind === "loading" && (
        <div className="it-empty" role="status">
          正在读取供应商群配置…
        </div>
      )}
      {state.kind === "error" && (
        <div className="it-empty" role="alert">
          <h2>群配置暂时无法加载</h2>
          <p>{state.message}</p>
          <Button onClick={reload}>重新加载</Button>
        </div>
      )}
      {state.kind === "ready" && (
        <>
          <p className="it-help">
            当前查询：{query.keyword || "全部关键词"} · 共 {state.data.total} 条配置
          </p>
          {state.data.items.length === 0 ? (
            <div className="it-empty">
              <h2>没有符合条件的供应商群配置</h2>
              <p>点击“新增配置”，选择供应商并查询对应的企微群。</p>
            </div>
          ) : (
            <div
              className="it-table-wrap sg-table"
              role="region"
              aria-label="供应商群配置，可横向滚动"
              // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex -- 宽表支持键盘聚焦滚动。
              tabIndex={0}
            >
              <table>
                <thead>
                  <tr>
                    <th scope="col">供应商 / NS 环境</th>
                    <th scope="col">企微外部群</th>
                    <th scope="col">群主</th>
                    <th scope="col">状态 / 更新时间</th>
                    <th scope="col">操作</th>
                  </tr>
                </thead>
                <tbody>
                  {state.data.items.map((item) => (
                    <tr key={JSON.stringify([item.account, item.supplierId])}>
                      <td>
                        <strong>{item.supplierName}</strong>
                        <span className="it-secondary">
                          {item.account} · {item.supplierId}
                        </span>
                      </td>
                      <td>
                        {item.groupName}
                        <span className="it-secondary">{item.chatId}</span>
                      </td>
                      <td>
                        {item.employee}
                        <span className="it-secondary">{item.userid}</span>
                      </td>
                      <td>
                        {item.enabled ? "启用" : "停用"}
                        <span className="it-secondary">
                          {new Date(item.updatedAt).toLocaleString("zh-CN", { timeZone: "Asia/Shanghai" })}
                        </span>
                      </td>
                      <td>
                        <Button
                          disabled={!state.data.manage.allowed || editor !== undefined}
                          onClick={() => {
                            setFeedback(null);
                            setEditor(item);
                          }}
                        >
                          修改
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <Pagination
            label="供应商群配置分页"
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
