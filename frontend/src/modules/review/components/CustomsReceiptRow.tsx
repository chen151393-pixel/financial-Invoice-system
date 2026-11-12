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

/** 一张海关回执：主行 + 展开后的明细比对。重新匹配由后端按当前 NS 报关单重算。 */
export function CustomsReceiptRow({
  receipt,
  open,
  busy,
  onToggle,
  onRematch,
}: {
  receipt: CustomsReceipt;
  open: boolean;
  busy: boolean;
  onToggle: () => void;
  onRematch: () => void;
}) {
  const needsAction = STATUS_TONE[receipt.status] === "warning";
  const detailId = `customs-receipt-${receipt.id}`;
  return (
    <tbody>
      <tr className={`fr-declaration-row${open ? " is-open" : ""}${needsAction ? " is-alert" : ""}`}>
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
        <td className="fr-declaration-action">
          <Button
            size="sm"
            disabled={busy}
            aria-label={`重新匹配报关单 ${receipt.declarationNo}`}
            onClick={onRematch}
          >
            重新匹配
          </Button>
        </td>
      </tr>
      <tr id={detailId} className="fr-declaration-detail" hidden={!open}>
        <td colSpan={7}>
          {open && (
            <div className="cm-detail">
              {(receipt.status === "ns_missing" || receipt.status === "ns_duplicate") && (
                <Alert tone="warning">
                  {receipt.statusNote}。NS
                  同步或修正后点击“重新匹配”；回执及境外收货人已保留，匹配后自动关联。
                </Alert>
              )}
              <CustomsCompareTable declarationNo={receipt.declarationNo} groups={receipt.groups} />
              <p className="cm-meta">
                来源文件 {receipt.fileName} · 第 {receipt.revision} 版 · 导入于 {time(receipt.importedAt)} ·
                比对于 {time(receipt.matchedAt)}
              </p>
            </div>
          )}
        </td>
      </tr>
    </tbody>
  );
}
