import type { ReactNode } from "react";
import { Badge, Card, CardHeader, DataTable } from "../../../shared/components/ui";
import type { InvoiceItem, InvoiceMatching } from "../types/matching";

/** 整张发票票面：购销双方、商品明细与合计；数值均为后端文本，选中行只做高亮。 */
export function InvoicePaper({
  value,
  selectedId,
  actions,
}: {
  value: InvoiceMatching;
  selectedId: string | null;
  actions?: ReactNode;
}) {
  const { invoice, paper, items } = value;
  const money = (text: string | null) => (text === null ? "—" : `¥${text}`);
  return (
    <Card className="matching-paper" aria-label="发票票面">
      <CardHeader
        title={
          <span className="matching-row">
            {paper.invoiceType || "进项发票"}
            <Badge tone={invoice.status === "normal" ? "success" : "warning"}>{invoice.statusLabel}</Badge>
          </span>
        }
        description={`发票号码 ${invoice.number} · 开票日期 ${invoice.date || "未提供"} · ${invoice.currency}`}
        actions={actions}
      />
      <div className="matching-paper__parties">
        <section aria-label="购买方">
          <small>购买方</small>
          <strong>{invoice.buyer || "票面未提供购买方"}</strong>
          <span>{paper.buyerTaxNo || "纳税人识别号未提供"}</span>
        </section>
        <section aria-label="销售方">
          <small>销售方</small>
          <strong>{invoice.seller || "票面未提供销售方"}</strong>
          <span>{paper.sellerTaxNo || "纳税人识别号未提供"}</span>
        </section>
      </div>
      <DataTable<InvoiceItem>
        label="发票商品明细"
        rows={items}
        rowKey={(row) => row.id}
        density="compact"
        minWidth={880}
        rowTone={(row) => (row.id === selectedId ? "accent" : undefined)}
        columns={[
          {
            key: "line",
            header: "行号",
            width: "56px",
            render: (row) => (
              <>
                {row.lineNo || "—"}
                {row.id === selectedId && <span className="ui-sr-only">（当前核对行）</span>}
              </>
            ),
          },
          {
            key: "item",
            header: "项目名称",
            render: (row) => (
              <span className="matching-cell">
                {row.item || "未提供品名"}
                {!row.active && <small>历史明细，已停用</small>}
              </span>
            ),
          },
          { key: "spec", header: "规格型号", render: (row) => row.specification || "—" },
          { key: "unit", header: "单位", width: "64px", render: (row) => row.unit || "—" },
          { key: "quantity", header: "数量", align: "right", render: (row) => row.quantity ?? "—" },
          { key: "price", header: "单价", align: "right", render: (row) => row.unitPrice ?? "—" },
          { key: "net", header: "金额", align: "right", render: (row) => money(row.net) },
          { key: "rate", header: "税率", align: "right", width: "64px", render: (row) => row.taxRate ?? "—" },
          { key: "tax", header: "税额", align: "right", render: (row) => money(row.tax) },
        ]}
      />
      <dl className="matching-paper__totals">
        <div>
          <dt>合计金额</dt>
          <dd>{money(paper.net)}</dd>
        </div>
        <div>
          <dt>合计税额</dt>
          <dd>{money(paper.tax)}</dd>
        </div>
        <div className="matching-paper__gross">
          <dt>价税合计（小写）</dt>
          <dd>{money(paper.gross)}</dd>
        </div>
      </dl>
      <p className="matching-paper__remark">
        <span>备注</span>
        {invoice.remark || "票面无备注"}
      </p>
    </Card>
  );
}
