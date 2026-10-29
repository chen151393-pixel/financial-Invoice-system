import { useState, type ReactNode } from "react";
import { Button, EmptyState, ErrorState, Skeleton } from "../../../shared/components/ui";
import type { ComparisonGroup, ComparisonState, PurchaseLine } from "../types";
import { DeclarationRow } from "./DeclarationRow";
import { PurchaseDialog } from "./PurchaseDialog";
import "./review.css";

// 主行列宽（不含勾选列）；批量模式在最前加 3% 的勾选列，从销售单号列让出
const COLUMN_WIDTHS = [13, 16, 11, 14, 15, 10, 9, 12];
const BATCH_WIDTHS = [3, 13, 16, 11, 14, 12, 10, 9, 12];

/**
 * 报关单列表：工具条（汇总、展开收起、刷新、批量审核）+ 主行表格。
 * 勾选框只在点击「批量审核通过」进入批量模式后出现，且只对后端允许审核的报关单开放。
 */
export function FinanceComparison({
  state,
  busy,
  onReview,
  onBatchApprove,
  onRetry,
  pagination,
}: {
  state: ComparisonState;
  busy: boolean;
  onReview: (group: ComparisonGroup) => void;
  onBatchApprove?: (groups: ComparisonGroup[]) => void;
  onRetry: () => void;
  pagination?: ReactNode;
}) {
  const [expanded, setExpanded] = useState<string[]>([]);
  const [batch, setBatch] = useState(false);
  const [checked, setChecked] = useState<string[]>([]);
  const [selected, setSelected] = useState<PurchaseLine | null>(null);
  if (state.kind === "loading") return <Skeleton label="正在读取报关单与关联采购" />;
  if (state.kind !== "ready")
    return state.kind === "error" ? (
      <ErrorState
        title="报关单暂时无法加载"
        message={state.message}
        action={<Button onClick={onRetry}>重新查询</Button>}
      />
    ) : (
      <EmptyState
        title="查询报关单"
        description="填写 CD 编号、PL 单号或子采购单号，查看报关与关联采购明细。"
      />
    );
  const { result } = state;
  // 可勾选范围只限当前页、后端允许审核的报关单
  const selectable = result.groups.filter((g) => g.review.status === "pending" && g.review.allowed);
  const chosen = selectable.filter((g) => checked.includes(g.id));
  const allChosen = selectable.length > 0 && chosen.length === selectable.length;
  const widths = batch ? BATCH_WIDTHS : COLUMN_WIDTHS;
  function exitBatch() {
    setBatch(false);
    setChecked([]);
  }
  return (
    <div className="fr-preview">
      <div className="fr-results">
        <p>
          {result.counts.shown} 张报关单 · {result.counts.customs} 条报关行 · {result.counts.purchase}{" "}
          条子采购行
          {batch && (
            <>
              {" "}
              · 已勾选 <b>{chosen.length}</b> 张（本页可审核 {selectable.length} 张）
            </>
          )}
        </p>
        <div className="fr-results__actions" role="group" aria-label="列表操作">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setExpanded(result.groups.map((group) => group.id))}
          >
            全部展开
          </Button>
          <Button variant="ghost" size="sm" onClick={() => setExpanded([])}>
            全部收起
          </Button>
          <Button size="sm" disabled={busy} onClick={onRetry}>
            刷新列表
          </Button>
          {onBatchApprove &&
            (batch ? (
              <>
                <Button size="sm" disabled={busy} onClick={exitBatch}>
                  取消批量
                </Button>
                <Button
                  size="sm"
                  variant="primary"
                  disabled={busy || chosen.length === 0}
                  onClick={() => onBatchApprove(chosen)}
                >
                  确认审核通过（{chosen.length}）
                </Button>
              </>
            ) : (
              <Button
                size="sm"
                variant="primary"
                disabled={busy || selectable.length === 0}
                title={selectable.length === 0 ? "本页没有可审核的报关单" : undefined}
                onClick={() => setBatch(true)}
              >
                批量审核通过
              </Button>
            ))}
        </div>
      </div>
      {!result.groups.length ? (
        <EmptyState title="没有符合条件的报关单" description="请调整查询条件或审核状态。" />
      ) : (
        /* 宽表格需要键盘聚焦后横向滚动，保持原生表格语义。 */
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
              {widths.map((width, index) => (
                <col key={index} style={{ width: `${width}%` }} />
              ))}
            </colgroup>
            <thead>
              <tr>
                {batch && (
                  <th scope="col" className="fr-check-cell">
                    {selectable.length > 0 && (
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
                )}
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
                  checkable={batch}
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
      )}
      {pagination}
      {selected && <PurchaseDialog line={selected} onClose={() => setSelected(null)} />}
    </div>
  );
}
