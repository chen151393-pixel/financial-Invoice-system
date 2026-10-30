import { Card, CardContent, CardHeader } from "../../../shared/components/ui";
import type { InvoiceItem, InvoiceMatching } from "../types/matching";

/** 整单比对左侧的进项发票行摘要；自动建议与手动整单关联共用，数值均为后端返回原文。 */
export function InvoiceLineSide({
  invoice,
  item,
}: {
  invoice: InvoiceMatching["invoice"];
  item: InvoiceItem;
}) {
  return (
    <Card className="matching-source-side">
      <CardHeader title="进项发票行" description={invoice.number} />
      <CardContent>
        <p>{invoice.seller || "销售方未提供"}</p>
        <p className="matching-help">
          开票日期 {invoice.date || "—"} · 购买方 {invoice.buyer || "未提供"}
        </p>
        <strong>
          第 {item.lineNo || "—"} 行 · {item.item || "品名未提供"}
        </strong>
        <p>
          {item.quantity ?? "—"} {item.unit || ""} · 价税合计 {item.amount ?? "—"} {invoice.currency}
        </p>
        <p className="matching-help">
          金额 {item.net ?? "—"} · 税率 {item.taxRate ?? "—"} · 税额 {item.tax ?? "—"}
        </p>
      </CardContent>
    </Card>
  );
}
