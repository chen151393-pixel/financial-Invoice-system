import { Badge, Button, type Tone } from "../../../shared/components/ui";
import type { ComparisonGroup, PurchaseLine } from "../types";
import { CustomsRows } from "./CustomsRows";
import { FinanceIcon } from "./FinanceIcon";

// 审核状态 → 组件库徽标语义：待审核需财务处理（橙），通过为绿，未出库为中性
const STATUS_TONE: Record<string, Tone> = { approved: "success", pending: "warning", unshipped: "neutral" };

/** 第一层：一张报关单的单头行；展开后显示第二层报关行。批量模式才有勾选列，且只对后端允许审核的报关单开放。 */
export function DeclarationRow({
  group,
  open,
  checked,
  checkable,
  onToggle,
  onCheck,
  onReview,
  onSelectLine,
}: {
  group: ComparisonGroup;
  open: boolean;
  checked: boolean;
  // 批量模式：显示勾选列
  checkable: boolean;
  onToggle: () => void;
  onCheck: (checked: boolean) => void;
  onReview: () => void;
  onSelectLine: (line: PurchaseLine) => void;
}) {
  const { review } = group;
  const approved = review.status === "approved";
  const selectable = checkable && review.status === "pending" && review.allowed;
  return (
    <tbody>
      <tr
        className={`fr-declaration-row${checked ? " is-checked" : ""}${open ? " is-open" : ""}${
          group.marginAlert ? " is-alert" : ""
        }`}
      >
        {checkable && (
          <td className="fr-check-cell">
            {selectable && (
              <input
                type="checkbox"
                checked={checked}
                aria-label={`选择报关单：${group.recordNumber}`}
                onChange={(event) => onCheck(event.target.checked)}
              />
            )}
          </td>
        )}
        <th scope="row">
          <button
            className="fr-declaration-toggle"
            aria-label={`${open ? "收起" : "展开"}报关单：${group.recordNumber}`}
            aria-expanded={open}
            aria-controls={`declaration-${group.id}`}
            onClick={onToggle}
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
        <td>{group.salesOrders || "未提供"}</td>
        <td>
          {group.customsCount} 条报关行<small>{group.purchaseCount} 条子采购行</small>
        </td>
        <td>
          <span className="fr-status-badges">
            <span title={review.reason}>
              <Badge tone={STATUS_TONE[review.status] ?? "neutral"}>{review.label}</Badge>
            </span>
            {/* 申报幅度为负时突出显示；可自动审核为后端预判，悬停显示依据 */}
            {group.marginAlert && <Badge tone="danger">申报幅度异常</Badge>}
            {group.autoReview?.eligible && (
              <span title="关联、金额、币种齐全且申报幅度正常">
                <Badge tone="info">可自动审核</Badge>
              </span>
            )}
          </span>
        </td>
        <td className="fr-declaration-action">
          <Button
            variant={approved ? "secondary" : "primary"}
            disabled={!review.allowed && !approved}
            title={review.reason}
            aria-label={`${approved ? "查看审核记录" : "审核通过"}：${group.recordNumber}`}
            onClick={onReview}
          >
            {approved ? "查看记录" : "审核通过"}
          </Button>
        </td>
      </tr>
      <tr id={`declaration-${group.id}`} className="fr-declaration-detail" hidden={!open}>
        <td colSpan={checkable ? 9 : 8}>
          {open && (
            <>
              {review.reason && <p className="fr-review-reason">{review.reason}</p>}
              <CustomsRows group={group} selectLine={onSelectLine} />
            </>
          )}
        </td>
      </tr>
    </tbody>
  );
}
