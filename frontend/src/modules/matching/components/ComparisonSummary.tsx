import { Card, CardContent, CardHeader } from "../../../shared/components/ui";
import type { InvoiceItem, InvoiceMatching, PurchaseSide } from "../types/matching";

export function ComparisonSummary({
  invoice,
  item,
  purchase,
}: {
  invoice: InvoiceMatching["invoice"];
  item: InvoiceItem;
  purchase: PurchaseSide | null;
}) {
  return (
    <div className="matching-comparison-sides">
      <Card className="matching-source-side">
        <CardHeader title="进项发票" description={invoice.number} />
        <CardContent>
          <p>{invoice.seller || "销售方未提供"}</p>
          <p className="matching-help">
            开票日期 {invoice.date || "—"} · 购买方 {invoice.buyer || "未提供"}
          </p>
          <strong>
            第 {item.lineNo || "—"} 行 · {item.item || "品名未提供"}
          </strong>
          <p>
            {item.quantity ?? "—"} {item.unit || ""} · 含税 {item.amount ?? "—"} {invoice.currency}
          </p>
        </CardContent>
      </Card>
      <Card className="matching-source-side matching-source-side--purchase">
        <CardHeader title="子采购行（开票口径）" description={purchase?.orderNo || "子采购信息不可用"} />
        <CardContent>
          <p>{purchase?.supplier || "—"}</p>
          <p className="matching-help">
            采购公司 {purchase?.company || "—"} · 报关单 {purchase?.recordNumber || "—"}
          </p>
          <strong>
            {purchase?.item || "—"} {purchase?.specification || ""}
          </strong>
          <p>
            {purchase?.expectedQuantity ?? "—"} {purchase?.unit || ""} · 含税{" "}
            {purchase?.expectedAmount ?? "—"} {purchase?.currency || "币种待核实"}
          </p>
          <p className="matching-help">
            剩余应开 {purchase?.remainingQuantity ?? "—"} / {purchase?.remainingAmount ?? "—"}
          </p>
          {purchase?.currencyNote && <p className="matching-help">{purchase.currencyNote}</p>}
        </CardContent>
      </Card>
    </div>
  );
}
