import { Link } from "react-router";
import { paths } from "../../../app/paths";
import { useEffect, useState } from "react";
import { Button } from "../../../shared/components/Button";
import { Pagination } from "../../../shared/components/Pagination";
import { openLocalSession } from "../../identity/api";
import { listTasks } from "../api/task";
import { TaskCountList, TaskGroupTable } from "../components/TaskGroupTable";
import type { TaskList, TaskListQuery } from "../types/task";
import "./task.css";

type Remote<T> = { kind: "loading" } | { kind: "error"; message: string } | { kind: "ready"; data: T };

export function TaskListPage() {
  const [query, setQuery] = useState<TaskListQuery>({
    keyword: "",
    account: "",
    groupBy: "supplier",
    status: "current",
    page: 1,
    pageSize: 20,
  });
  const [keyword, setKeyword] = useState("");
  const [account, setAccount] = useState("");
  const [accounts, setAccounts] = useState<string[]>([]);
  const [state, setState] = useState<Remote<TaskList>>({ kind: "loading" });
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    let active = true;
    async function load() {
      try {
        await openLocalSession();
        const data = await listTasks(query);
        if (active) {
          setState({ kind: "ready", data });
          setAccounts(data.accounts);
        }
      } catch (error) {
        if (active)
          setState({ kind: "error", message: error instanceof Error ? error.message : "开票任务加载失败" });
      }
    }
    void load();
    return () => {
      active = false;
    };
  }, [query, refresh]);
  function change(patch: Partial<TaskListQuery>) {
    setState({ kind: "loading" });
    setQuery((current) => ({ ...current, page: 1, ...patch }));
  }
  const busy = state.kind === "loading";
  return (
    <div className="it-page">
      <form
        className="it-search"
        onSubmit={(event) => {
          event.preventDefault();
          change({ keyword, account });
        }}
      >
        <label className="it-search__keyword">
          报关单 / 供应商 / 子采购单
          <input
            type="search"
            maxLength={120}
            placeholder="输入编号或名称"
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
          />
        </label>
        <label>
          NS 环境
          <select value={account} onChange={(e) => setAccount(e.target.value)}>
            <option value="">全部 NS 环境</option>
            {accounts.map((item) => (
              <option key={item}>{item}</option>
            ))}
          </select>
        </label>
        <Button variant="primary" type="submit" disabled={busy}>
          查询
        </Button>
        <Button
          disabled={busy}
          onClick={() => {
            setState({ kind: "loading" });
            setRefresh((n) => n + 1);
          }}
        >
          刷新
        </Button>
      </form>
      {(keyword !== query.keyword || account !== query.account) && (
        <p className="it-help" role="status">
          筛选条件已修改，点击「查询」生效；当前结果仍使用上次提交的条件。
        </p>
      )}
      <div className="it-toolbar">
        <div className="it-switch" role="group" aria-label="任务分组方式">
          <Button
            aria-pressed={query.groupBy === "supplier"}
            disabled={busy}
            onClick={() => change({ groupBy: "supplier" })}
          >
            按供应商
          </Button>
          <Button
            aria-pressed={query.groupBy === "declaration"}
            disabled={busy}
            onClick={() => change({ groupBy: "declaration" })}
          >
            按报关单
          </Button>
        </div>
        <label>
          任务版本
          <select
            aria-label="任务版本"
            value={query.status}
            disabled={busy}
            onChange={(e) => change({ status: e.target.value as TaskListQuery["status"] })}
          >
            <option value="current">当前任务</option>
            <option value="superseded">已被替代</option>
            <option value="all">全部版本</option>
          </select>
        </label>
      </div>
      <p className="it-help">
        两种视图展示同一批任务。待开票包含待保存合同、待通知供应商、等待开票及部分收票的任务，待处理可与其重叠；收票进度由发票比对通过的分配自动汇总。按完整分组分页。
      </p>
      {state.kind === "loading" && (
        <div className="it-empty" role="status">
          正在读取开票任务…
        </div>
      )}
      {state.kind === "error" && (
        <div className="it-empty" role="alert">
          <h2>开票任务暂时无法加载</h2>
          <p>{state.message}</p>
          <Button
            onClick={() => {
              setState({ kind: "loading" });
              setRefresh((n) => n + 1);
            }}
          >
            重新加载
          </Button>
        </div>
      )}
      {state.kind === "ready" && (
        <>
          <p className="it-help">
            当前查询范围：{query.keyword ? `“${query.keyword}”` : "全部关键词"} ·{" "}
            {query.account || "全部 NS 环境"}
          </p>
          <div className="it-result" role="status">
            共 {state.data.counts.tasks} 个任务 · {state.data.total} 个
            {query.groupBy === "supplier" ? "供应商分组" : "报关单分组"}
            <TaskCountList counts={state.data.counts} />
          </div>
          {state.data.groups.length ? (
            state.data.groups.map((group, index) => (
              <TaskGroupTable key={`${query.groupBy}:${group.id}`} group={group} first={index === 0} />
            ))
          ) : (
            <div className="it-empty">
              <h2>
                {query.keyword || query.account || query.status !== "current"
                  ? "没有符合条件的任务"
                  : "还没有开票任务"}
              </h2>
              <p>财务审核通过后按供应商、采购公司和币种自动生成任务；新链路之前的旧任务不迁移。</p>
              <Link to={paths.review}>前往财务核对</Link>
            </div>
          )}
          <Pagination
            label="开票任务分组分页"
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
