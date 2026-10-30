import { useState } from "react";
import "./workbench-todos.css";
import { Link } from "react-router";
import { matchingInvoicePath, paths, taskPath } from "../../../app/paths";
import { Badge, Button, ErrorState, Pagination, Skeleton, Tabs } from "../../../shared/components/ui";
import { money } from "../../../shared/format/money";
import {
  roleLabels,
  todoLabels,
  type Todo,
  type TodoKind,
  type Workbench,
  type WorkbenchQuery,
} from "../types/workbench";

function destination(row: Todo) {
  if (row.kind === "task") return taskPath(row.targetId);
  if (row.kind === "matching") return matchingInvoicePath(row.targetId);
  return `${paths.review}?${new URLSearchParams({ keyword: row.title })}`;
}

export function WorkbenchTodos({
  data,
  query,
  change,
  exporting,
  onExport,
  loading = false,
  error = "",
  onRetry,
}: {
  data: Workbench;
  query: WorkbenchQuery;
  change: (patch: Partial<WorkbenchQuery>) => void;
  exporting: boolean;
  onExport: () => void;
  loading?: boolean;
  error?: string;
  onRetry?: () => void;
}) {
  const [keyword, setKeyword] = useState(query.keyword);
  return (
    <section className="wb-panel wb-todos" aria-labelledby="wb-todos-title">
      <div className="wb-panel__head">
        <div>
          <h2 id="wb-todos-title">优先处理</h2>
          <p className="wb-panel__sub">按紧急程度排序 · 标签标明由财务还是采购处理</p>
        </div>
        <span className="wb-count">共 {data.counts.all} 项</span>
      </div>
      <div className="wb-todos__tabs">
        <Tabs
          label="待办分类"
          value={query.kind}
          onChange={(kind) => change({ kind })}
          items={(Object.keys(todoLabels) as TodoKind[]).map((kind) => ({
            key: kind,
            label: todoLabels[kind],
            count: data.filteredCounts[kind],
          }))}
        />
      </div>
      <form
        className="wb-search"
        onSubmit={(event) => {
          event.preventDefault();
          change({ keyword });
        }}
      >
        <label className="wb-search__input">
          <span className="wb-sr-only">搜索待办</span>
          <input
            value={keyword}
            onChange={(event) => setKeyword(event.target.value)}
            placeholder="搜索单号、供应商、PL 单号"
            maxLength={120}
          />
        </label>
        <Button type="submit">查询</Button>
        <label>
          <span className="wb-sr-only">待办排序</span>
          <select
            value={query.sort}
            onChange={(event) => change({ sort: event.target.value as WorkbenchQuery["sort"] })}
          >
            <option value="priority">优先处理问题单据</option>
            <option value="oldest">最早入库优先</option>
            <option value="newest">最新入库优先</option>
          </select>
        </label>
        <Button
          className="wb-export"
          onClick={onExport}
          disabled={loading || !!error || exporting || data.total === 0}
        >
          {exporting ? "正在导出…" : "↓ 导出全部结果"}
        </Button>
      </form>
      {query.keyword && (
        <p className="wb-applied">
          搜索：{query.keyword}{" "}
          <Button
            onClick={() => {
              setKeyword("");
              change({ keyword: "" });
            }}
          >
            清除搜索
          </Button>
        </p>
      )}
      <div className="wb-todos__results" aria-busy={loading}>
        {(loading || error) && (
          <div className="wb-todos__feedback">
            {loading ? (
              <Skeleton rows={3} label="正在读取待办列表…" />
            ) : (
              <ErrorState
                title="待办列表加载失败"
                message={error}
                action={<Button onClick={onRetry}>重新加载待办</Button>}
              />
            )}
          </div>
        )}
        <div className={loading || error ? "wb-todos__previous" : undefined} inert={loading || !!error}>
          <div className="wb-table-scroll" role="region" aria-label="待办表格，可横向滚动">
            <table className="wb-table">
              <thead>
                <tr>
                  <th className="wb-col-kind">事项</th>
                  <th className="wb-col-document">单据</th>
                  <th className="wb-col-supplier">供应商</th>
                  <th className="wb-col-amount wb-number">金额</th>
                  <th className="wb-col-wait wb-number">等待</th>
                  <th className="wb-col-status">原因</th>
                  <th className="wb-col-action">操作</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((row) => (
                  <tr key={row.key}>
                    <td>
                      <span className="wb-kind">
                        <Badge dot={false} tone={row.role === "finance" ? "info" : "warning"}>
                          {roleLabels[row.role]}
                        </Badge>
                        {todoLabels[row.kind]}
                      </span>
                    </td>
                    <td>
                      <Link to={destination(row)}>{row.title}</Link>
                      <small>{row.subtitle || "—"}</small>
                    </td>
                    <td>{row.party}</td>
                    <td className="wb-number">
                      {row.amount !== null ? `${row.currency || "币种待核实"} ${money(row.amount)}` : "—"}
                      <small>{row.amountLabel}</small>
                    </td>
                    <td className="wb-number">{row.waitingDays === null ? "—" : `${row.waitingDays} 天`}</td>
                    <td>
                      <span className={`wb-status${row.attention ? " wb-status--attention" : ""}`}>
                        {row.statusLabel}
                      </span>
                      <small>{row.reason}</small>
                    </td>
                    <td>
                      <Link to={destination(row)}>
                        {row.kind === "review" ? "去核对" : row.kind === "matching" ? "去比对" : "去跟进"} →
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {!data.items.length && (
            <div className="wb-empty" role="status">
              <strong>当前条件下没有待办</strong>
              <p>可调整分类或搜索条件，查看其他单据。</p>
              <Button
                onClick={() => {
                  setKeyword("");
                  change({ kind: "all", keyword: "" });
                }}
              >
                重置待办筛选
              </Button>
            </div>
          )}
        </div>
      </div>
      <Pagination
        label="待办分页"
        total={data.total}
        page={data.page}
        pageCount={data.pages}
        pageSize={data.pageSize}
        pageSizes={[5, 10, 20]}
        disabled={loading || !!error}
        onPageChange={(page) => change({ page })}
        onPageSizeChange={(pageSize) => change({ pageSize })}
      />
    </section>
  );
}
