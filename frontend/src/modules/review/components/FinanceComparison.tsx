import { useState, type ReactNode } from "react";
import { Button, Tabs } from "../../../shared/components/ui";
import type { ComparisonGroup, ComparisonState, PurchaseLine, ReviewFilter } from "../types";
import { DeclarationRow } from "./DeclarationRow";
import { PurchaseDialog } from "./ReviewDialog";
import "./review.css";

const FILTER_LABELS: Record<ReviewFilter, string> = {
  all: "全部报关单",
  pending: "待审核",
  approved: "审核通过",
};

export function FinanceComparison({
  state,
  filter = "all",
  onFilter,
  onReview,
  onBatchApprove,
  onRetry,
  pagination,
}: {
  state: ComparisonState;
  filter?: ReviewFilter;
  onFilter: (filter: ReviewFilter) => void;
  onReview: (group: ComparisonGroup) => void;
  onBatchApprove?: (groups: ComparisonGroup[]) => void;
  onRetry: () => void;
  pagination?: ReactNode;
}) {
  const [expanded, setExpanded] = useState<string[]>([]);
  const [checked, setChecked] = useState<string[]>([]);
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
  // 可勾选范围只限当前页、后端允许审核的报关单
  const selectable = result.groups.filter((g) => g.review.status === "pending" && g.review.allowed);
  const chosen = selectable.filter((g) => checked.includes(g.id));
  const allChosen = selectable.length > 0 && chosen.length === selectable.length;
  return (
    <div className="fr-preview">
      {result.notices.map((notice) => (
        <p className="fr-review-reason" key={notice}>
          {notice}
        </p>
      ))}
      <div className="fr-toolbar">
        <Tabs
          label="按审核状态筛选"
          value={filter}
          onChange={onFilter}
          items={(Object.keys(FILTER_LABELS) as ReviewFilter[]).map((key) => ({
            key,
            label: FILTER_LABELS[key],
            count: result.counts[key] ?? 0,
          }))}
        />
        <div className="fr-tree-actions">
          <button
            onClick={() => {
              setExpanded(result.groups.map((group) => group.id));
            }}
          >
            全部展开
          </button>
          <span aria-hidden="true">/</span>
          <button
            onClick={() => {
              setExpanded([]);
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
        {onBatchApprove && chosen.length > 0 ? (
          <div className="fr-batch-bar" role="group" aria-label="批量审核">
            <span>
              当前页已选 <b>{chosen.length}</b> 张（本页可审核 {selectable.length} 张）
            </span>
            <Button onClick={() => setChecked([])}>取消选择</Button>
            <Button variant="primary" onClick={() => onBatchApprove(chosen)}>
              批量审核通过
            </Button>
          </div>
        ) : (
          <span>数据来源：已入库单据</span>
        )}
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
              <caption className="fr-sr-only">报关单主行，展开查看报关与子采购对照明细</caption>
              <colgroup>
                {[3, 12, 16, 11, 15, 15, 10, 8, 10].map((width, index) => (
                  <col key={index} style={{ width: `${width}%` }} />
                ))}
              </colgroup>
              <thead>
                <tr>
                  <th scope="col" className="fr-check-cell">
                    {onBatchApprove && selectable.length > 0 && (
                      <input
                        type="checkbox"
                        checked={allChosen}
                        aria-label="选择当前页全部可审核的报关单"
                        onChange={(event) =>
                          setChecked(event.target.checked ? selectable.map((group) => group.id) : [])
                        }
                      />
                    )}
                  </th>
                  <th scope="col" className="fr-toggle-heading">
                    主报关单（NS 编号）
                  </th>
                  <th scope="col">真实报关单号</th>
                  <th scope="col">PL 单号</th>
                  <th scope="col">申报抬头</th>
                  <th scope="col">销售单号</th>
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
                  <DeclarationRow
                    key={group.id}
                    group={group}
                    open={open}
                    checked={checked.includes(group.id)}
                    checkable={Boolean(onBatchApprove)}
                    onToggle={() => {
                      setExpanded((current) =>
                        open ? current.filter((id) => id !== group.id) : [...current, group.id],
                      );
                    }}
                    onCheck={(value) =>
                      setChecked((current) =>
                        value ? [...current, group.id] : current.filter((id) => id !== group.id),
                      )
                    }
                    onReview={() => onReview(group)}
                    onSelectLine={setSelected}
                  />
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
