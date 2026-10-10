import { useState, type ReactNode } from "react";
import { Button } from "../../../shared/components/Button";
import type { ComparisonGroup, ComparisonState, PurchaseLine, ReviewFilter } from "../types";
import { CustomsRows } from "./CustomsRows";
import { FinanceIcon } from "./FinanceIcon";
import { PurchaseDialog } from "./ReviewDialog";
import "./pl-comparison.css";

export function FinanceComparison({
  state,
  filter = "all",
  onFilter,
  onReview,
  onRetry,
  pagination,
}: {
  state: ComparisonState;
  filter?: ReviewFilter;
  onFilter: (filter: ReviewFilter) => void;
  onReview: (group: ComparisonGroup) => void;
  onRetry: () => void;
  pagination?: ReactNode;
}) {
  const [expanded, setExpanded] = useState<string[]>([]);
  const [rows, setRows] = useState<Record<string, string[]>>({});
  const [selected, setSelected] = useState<PurchaseLine | null>(null);
  if (state.kind !== "ready")
    return (
      <section className="fr-preview fr-empty" role={state.kind === "error" ? "alert" : "status"}>
        <h2>
          {state.kind === "idle"
            ? "查询报关单"
            : state.kind === "loading"
              ? "正在读取报关单与关联采购…"
              : "查询失败"}
        </h2>
        <p>
          {state.kind === "error"
            ? state.message
            : state.kind === "idle"
              ? "填写CD编号、PL单号或日期范围，查看报关与关联采购明细。"
              : "请稍候，查询完成后将默认收起明细。"}
        </p>
        {state.kind === "error" && <Button onClick={onRetry}>重新查询</Button>}
      </section>
    );
  const { result } = state;
  const labels: Record<Exclude<ReviewFilter, "blocked">, string> = {
    all: "全部报关单",
    pending: "待审核",
    approved: "审核通过",
  };
  return (
    <div className="fr-preview">
      {result.notices.map((notice) => (
        <p className="fr-review-reason" key={notice}>
          {notice}
        </p>
      ))}
      <div className="fr-toolbar">
        <div className="fr-filters" role="group" aria-label="按审核状态筛选">
          {(Object.keys(labels) as Array<keyof typeof labels>).map((key) => (
            <button key={key} aria-pressed={filter === key} onClick={() => onFilter(key)}>
              {labels[key]} <span>{result.counts[key]}</span>
            </button>
          ))}
        </div>
        <div className="fr-tree-actions">
          <button
            onClick={() => {
              setExpanded(result.groups.map((group) => group.id));
              setRows(
                Object.fromEntries(
                  result.groups.map((group) => [group.id, group.customsLines.map((row) => row.id)]),
                ),
              );
            }}
          >
            全部展开
          </button>
          <span aria-hidden="true">/</span>
          <button
            onClick={() => {
              setExpanded([]);
              setRows({});
            }}
          >
            全部收起
          </button>
        </div>
      </div>
      <div className="fr-results">
        <p>
          {result.counts.shown} 张报关单 · {result.counts.customs} 条报关行 · {result.counts.purchase}{" "}
          条子采购行
        </p>
        <span>
          {result.source === "database" ? "数据来源：已入库单据" : `NS读取：${result.readCompletedAt}`}
        </span>
      </div>
      {!result.groups.length ? (
        <div className="fr-declaration-list">
          <section className="fr-empty fr-empty--in-list">
            <h2>没有符合条件的报关单</h2>
            <p>请调整查询条件或审核状态。</p>
          </section>
          {pagination}
        </div>
      ) : (
        <div className="fr-declaration-list">
          {/* 宽表格需要键盘聚焦后横向滚动，保持原生表格语义。 */}
          <div
            className="fr-declaration-scroll"
            role="region"
            aria-label="主报关单列表，可横向滚动"
            // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex -- 原生宽表区域需支持键盘聚焦及横向滚动。
            tabIndex={0}
          >
            <table className="fr-declaration-table">
              <caption className="fr-sr-only">报关单、报关明细及关联子采购逐级展开</caption>
              <colgroup>
                {[19, 20, 14, 17, 10, 10, 10].map((width, index) => (
                  <col key={index} style={{ width: `${width}%` }} />
                ))}
              </colgroup>
              <thead>
                <tr>
                  <th scope="col" className="fr-toggle-heading">
                    主报关单（NS 编号）
                  </th>
                  <th scope="col">真实报关单号</th>
                  <th scope="col">PL 单号</th>
                  <th scope="col">申报公司</th>
                  <th scope="col">关联明细</th>
                  <th scope="col">审核状态</th>
                  <th scope="col" className="fr-declaration-action">
                    操作
                  </th>
                </tr>
              </thead>
              {result.groups.map((group) => {
                const open = expanded.includes(group.id);
                return (
                  <tbody key={group.id}>
                    <tr className="fr-declaration-row">
                      <th scope="row">
                        <button
                          className="fr-declaration-toggle"
                          aria-label={`${open ? "收起" : "展开"}报关单：${group.recordNumber}`}
                          aria-expanded={open}
                          aria-controls={`declaration-${group.id}`}
                          onClick={() => {
                            setExpanded((current) =>
                              open ? current.filter((id) => id !== group.id) : [...current, group.id],
                            );
                            setRows((current) => ({ ...current, [group.id]: [] }));
                          }}
                        >
                          <span className={`fr-chevron ${open ? "open" : ""}`}>
                            <FinanceIcon kind="chevron" />
                          </span>
                          <strong>{group.recordNumber}</strong>
                        </button>
                      </th>
                      <td className="fr-declaration-number">{group.declaration || "未填写"}</td>
                      <td>
                        {group.pl || "未提供"}
                        {group.account && <small>NS {group.account}</small>}
                      </td>
                      <td>{group.company || "未提供"}</td>
                      <td>
                        {group.customsCount} 条报关行<small>{group.purchaseCount} 条子采购行</small>
                      </td>
                      <td>
                        <span
                          className={`fr-status fr-status--${group.review.status}`}
                          title={group.review.reason}
                        >
                          <FinanceIcon
                            kind={
                              group.review.status === "approved"
                                ? "check"
                                : group.review.status === "blocked"
                                  ? "alert"
                                  : "clock"
                            }
                          />
                          {group.review.label}
                        </span>
                      </td>
                      <td className="fr-declaration-action">
                        <Button
                          variant={group.review.status === "approved" ? "secondary" : "primary"}
                          disabled={!group.review.allowed && group.review.status !== "approved"}
                          title={group.review.reason}
                          aria-label={`${group.review.status === "approved" ? "查看审核记录" : "审核通过"}：${group.recordNumber}`}
                          onClick={() => onReview(group)}
                        >
                          {group.review.status === "approved" ? "查看记录" : "审核通过"}
                        </Button>
                      </td>
                    </tr>
                    <tr id={`declaration-${group.id}`} className="fr-declaration-detail" hidden={!open}>
                      <td colSpan={7}>
                        {open && (
                          <>
                            {group.review.reason && <p className="fr-review-reason">{group.review.reason}</p>}
                            <CustomsRows
                              group={group}
                              expandedRows={rows[group.id] || []}
                              toggleRow={(id) =>
                                setRows((current) => {
                                  const list = current[group.id] || [];
                                  return {
                                    ...current,
                                    [group.id]: list.includes(id)
                                      ? list.filter((value) => value !== id)
                                      : [...list, id],
                                  };
                                })
                              }
                              selectLine={setSelected}
                            />
                          </>
                        )}
                      </td>
                    </tr>
                  </tbody>
                );
              })}
            </table>
          </div>
          {pagination}
        </div>
      )}
      {selected && <PurchaseDialog line={selected} onClose={() => setSelected(null)} />}
    </div>
  );
}
