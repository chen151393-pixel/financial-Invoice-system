import { Alert, Badge, Button, type Tone } from "../../../shared/components/ui";
import type { ReviewLinks } from "../approval-progress";
import type { CustomsMatchStatus, CustomsReceipt } from "../customs-types";
import { ApprovalProgressCells, ApprovalProgressDetail } from "./ApprovalProgressCells";
import { CustomsCompareTable } from "./CustomsCompareTable";
import { FinanceIcon } from "./FinanceIcon";

// 后端比对状态 → 组件库徽标语义：一致为绿，需处理为橙
const STATUS_TONE: Record<CustomsMatchStatus, Tone> = {
  matched: "success",
  split_matched: "success",
  different: "warning",
  ns_missing: "warning",
  ns_duplicate: "warning",
};
const CONSIGNEE_TONE: Record<CustomsReceipt["consignee"]["state"], Tone> = {
  saved: "success",
  empty: "neutral",
  pending: "info",
};
const TOTAL_COMPARISON: Record<CustomsReceipt["totalComparison"], { tone: Tone; label: string }> = {
  matched: { tone: "success", label: "总价一致" },
  different: { tone: "warning", label: "总价不一致" },
  partial: { tone: "neutral", label: "部分总价未比对" },
  not_compared: { tone: "neutral", label: "总价未比对" },
};

const time = (value: string) =>
  value ? new Date(value).toLocaleString("zh-CN", { timeZone: "Asia/Shanghai", hour12: false }) : "—";

/** 海关回执主行复用财务核对的勾选、状态与审核按钮样式。 */
export function CustomsReceiptRow({
  receipt,
  open,
  busy,
  onToggle,
  batch,
  selected,
  onSelect,
  onApprove,
  links,
}: {
  receipt: CustomsReceipt;
  open: boolean;
  busy: boolean;
  onToggle: () => void;
  batch: boolean;
  selected: boolean;
  onSelect: (checked: boolean) => void;
  onApprove: () => void;
  links?: ReviewLinks;
}) {
  const needsAction = STATUS_TONE[receipt.status] === "warning";
  const total = receipt.nsLineCount === null ? undefined : TOTAL_COMPARISON[receipt.totalComparison];
  const detailId = `customs-receipt-${receipt.id}`;
  return (
    <tbody>
      <tr
        className={`fr-declaration-row${selected ? " is-checked" : ""}${open ? " is-open" : ""}${needsAction ? " is-alert" : ""}`}
      >
        {batch && (
          <td className="fr-check-cell">
            {receipt.approval.allowed && (
              <input
                type="checkbox"
                aria-label={`选择回执 ${receipt.declarationNo}`}
                checked={selected}
                disabled={busy}
                onChange={(event) => onSelect(event.target.checked)}
              />
            )}
          </td>
        )}
        <th scope="row">
          <button
            type="button"
            className="fr-declaration-toggle"
            aria-label={`${open ? "收起" : "展开"}报关单 ${receipt.declarationNo} 的明细比对`}
            aria-expanded={open}
            aria-controls={detailId}
            onClick={onToggle}
          >
            <span className={`fr-chevron ${open ? "open" : ""}`}>
              <FinanceIcon kind="chevron" />
            </span>
            <span className="cm-number">
              <strong>{receipt.declarationNo}</strong>
              <small>
                关单信息 {receipt.customsDoc || "未提供"} · {receipt.usageFlag || "使用标志未提供"}
              </small>
            </span>
          </button>
        </th>
        <td>
          {receipt.exportDate || "未提供"}
          {receipt.taxType && ` · ${receipt.taxType}`}
          <small>
            NS {receipt.nsLineCount ?? "—"} 行 / 海关 {receipt.itemCount} 项
          </small>
          {receipt.nsRecordNo && <small>NS 记录 {receipt.nsRecordNo}</small>}
        </td>
        <td>
          <span className="cm-consignee">
            <span>{receipt.consignee.value || "—"}</span>
            <Badge tone={CONSIGNEE_TONE[receipt.consignee.state]}>{receipt.consignee.label}</Badge>
          </span>
          <small>{receipt.consignee.note}</small>
        </td>
        <td>
          <span className="fr-status-badges">
            <Badge tone={STATUS_TONE[receipt.status]}>
              {receipt.totalComparison === "different" && receipt.status === "matched"
                ? "数量一致"
                : receipt.statusLabel}
            </Badge>
            {total && <Badge tone={total.tone}>{total.label}</Badge>}
          </span>
          {receipt.statusNote && <small>{receipt.statusNote}</small>}
        </td>
        <ApprovalProgressCells
          page="customs"
          progress={receipt.approvalProgress}
          declarationNo={receipt.declarationNo}
          links={links}
          canReview={!busy && receipt.approval.allowed}
          onReview={onApprove}
          onDetails={onToggle}
          expanded={open}
          customsFallback={
            <span className="fr-status-badges">
              <Badge tone={receipt.approval.approved ? "success" : "warning"}>{receipt.approval.label}</Badge>
              {receipt.approval.autoAllowed && <Badge tone="info">可自动审核</Badge>}
            </span>
          }
          localAction={
            !receipt.approval.approved &&
            (!receipt.approvalProgress || receipt.approval.allowed) && (
              <Button
                size="sm"
                variant={receipt.approvalProgress ? "secondary" : "primary"}
                disabled={busy || !receipt.approval.allowed}
                title={receipt.approval.reason}
                aria-label={`审核通过：${receipt.declarationNo}`}
                onClick={onApprove}
              >
                {receipt.approvalProgress ? "审核海关回执" : "审核通过"}
              </Button>
            )
          }
        />
      </tr>
      <tr id={detailId} className="fr-declaration-detail" hidden={!open}>
        <td colSpan={batch ? 9 : 8}>
          {open && (
            <div className="cm-detail">
              <ApprovalProgressDetail
                progress={receipt.approvalProgress}
                links={links}
                page="customs"
                declarationNo={receipt.declarationNo}
              />
              {receipt.status === "different" && receipt.approval.allowed && (
                <Alert tone="warning">审核本张回执时需填写差异说明。</Alert>
              )}
              {(receipt.status === "ns_missing" || receipt.status === "ns_duplicate") && (
                <Alert tone="warning">
                  {receipt.statusNote}。NS 同步或修正后刷新列表核对；回执及境外收货人已保留，匹配后自动关联。
                </Alert>
              )}
              <CustomsCompareTable declarationNo={receipt.declarationNo} groups={receipt.groups} />
              <p className="cm-meta">
                来源文件 {receipt.fileName} · 第 {receipt.revision} 版 · 导入于 {time(receipt.importedAt)} ·
                比对于 {time(receipt.matchedAt)}
              </p>
              {receipt.approval.approved && (
                <p className="cm-meta">
                  {receipt.approval.label} · 操作人 {receipt.approval.approvedBy} ·{" "}
                  {time(receipt.approval.approvedAt)}
                  {receipt.approval.note && ` · 说明：${receipt.approval.note}`}
                </p>
              )}
            </div>
          )}
        </td>
      </tr>
    </tbody>
  );
}
