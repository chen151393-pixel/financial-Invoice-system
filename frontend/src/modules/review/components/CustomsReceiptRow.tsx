import { Alert, Badge, Button, type Tone } from "../../../shared/components/ui";
import type { CustomsMatchStatus, CustomsReceipt } from "../customs-types";
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
}: {
  receipt: CustomsReceipt;
  open: boolean;
  busy: boolean;
  onToggle: () => void;
  batch: boolean;
  selected: boolean;
  onSelect: (checked: boolean) => void;
  onApprove: () => void;
}) {
  const needsAction = STATUS_TONE[receipt.status] === "warning";
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
        <td className="fr-declaration-number">{receipt.exportDate || "未提供"}</td>
        <td>{receipt.taxType || "—"}</td>
        <td className="fr-declaration-number">
          NS {receipt.nsLineCount ?? "—"} 行 / 海关 {receipt.itemCount} 项
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
          <Badge tone={STATUS_TONE[receipt.status]}>{receipt.statusLabel}</Badge>
          {receipt.statusNote && <small>{receipt.statusNote}</small>}
        </td>
        <td>
          <span className="fr-status-badges">
            <Badge tone={receipt.approval.approved ? "success" : "warning"}>{receipt.approval.label}</Badge>
            {receipt.approval.autoAllowed && <Badge tone="info">可自动审核</Badge>}
          </span>
          {!receipt.approval.approved && receipt.approval.reason && <small>{receipt.approval.reason}</small>}
          {receipt.approval.approved && <small>{time(receipt.approval.approvedAt)}</small>}
        </td>
        <td className="fr-declaration-action">
          {!receipt.approval.approved && (
            <Button
              variant="primary"
              disabled={busy || !receipt.approval.allowed}
              title={receipt.approval.reason}
              aria-label={`审核通过：${receipt.declarationNo}`}
              onClick={onApprove}
            >
              审核通过
            </Button>
          )}
        </td>
      </tr>
      <tr id={detailId} className="fr-declaration-detail" hidden={!open}>
        <td colSpan={batch ? 9 : 8}>
          {open && (
            <div className="cm-detail">
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
