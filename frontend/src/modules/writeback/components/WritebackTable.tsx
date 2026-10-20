import { Link } from "react-router";
import { writebackRequestPath } from "../../../app/paths";
import { Button } from "../../../shared/components/Button";
import type { WritebackItem, WritebackPhase } from "../types";
import { WritebackPhaseTag } from "./WritebackPhaseTag";

const linkLabels: Partial<Record<WritebackPhase, string>> = {
  pending: "查看预览",
  executing: "查看进度",
  unknown: "核实结果",
  failed: "查看原因",
  succeeded: "查看记录",
};

function RowAction({
  item,
  busy,
  error,
  onPreview,
}: {
  item: WritebackItem;
  busy: boolean;
  error: string;
  onPreview: () => void;
}) {
  const label = linkLabels[item.phase];
  if (label && item.requestId)
    return (
      <div className="wb-action">
        <Link
          className={item.phase === "unknown" ? "ui-button ui-button--secondary wb-button-small" : undefined}
          to={writebackRequestPath(item.requestId)}
        >
          {label}
        </Link>
        {item.note && <span className={`wb-note wb-note--${item.phase}`}>{item.note}</span>}
      </div>
    );
  const reasonId = `wb-reason-${item.invoiceId}`;
  return (
    <div className="wb-action">
      <Button
        variant="primary"
        className="wb-button-small"
        disabled={busy || !item.preview.allowed}
        aria-describedby={item.preview.allowed ? undefined : reasonId}
        onClick={onPreview}
      >
        {busy ? "正在生成…" : "生成预览"}
      </Button>
      {!item.preview.allowed && (
        <span id={reasonId} className="wb-note wb-note--blocked">
          {item.preview.reason}
        </span>
      )}
      {error && (
        <span role="alert" className="wb-note wb-note--failed">
          {error}
        </span>
      )}
    </div>
  );
}

/** 回写候选与记录列表；金额、分配进度、状态文字均为后端文本。 */
export function WritebackTable({
  items,
  busyInvoice,
  error,
  onPreview,
}: {
  items: WritebackItem[];
  busyInvoice: string;
  error: { invoiceId: string; message: string } | null;
  onPreview: (invoiceId: string) => void;
}) {
  return (
    <div className="wb-table-scroll">
      <table className="wb-table">
        <thead>
          <tr>
            <th scope="col">发票号码</th>
            <th scope="col">开票日期</th>
            <th scope="col">供应商</th>
            <th scope="col" className="wb-num">
              价税合计
            </th>
            <th scope="col">子采购单</th>
            <th scope="col">分配</th>
            <th scope="col">回写状态</th>
            <th scope="col">操作</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.invoiceId}>
              <td className="wb-mono">{item.invoiceNo}</td>
              <td className="wb-nowrap">{item.invoiceDate}</td>
              <td>{item.vendorName}</td>
              <td className="wb-num">
                {item.amount} <span className="wb-muted">{item.currency}</span>
              </td>
              <td>{item.purchaseOrders}</td>
              <td className="wb-nowrap">{item.allocation}</td>
              <td>
                <WritebackPhaseTag phase={item.phase} label={item.label} />
              </td>
              <td>
                <RowAction
                  item={item}
                  busy={busyInvoice === item.invoiceId}
                  error={error?.invoiceId === item.invoiceId ? error.message : ""}
                  onPreview={() => onPreview(item.invoiceId)}
                />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
