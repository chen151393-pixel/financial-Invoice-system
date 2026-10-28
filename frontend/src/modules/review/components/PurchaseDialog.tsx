import { DataTable, Dialog, SectionTitle } from "../../../shared/components/ui";
import type { PurchaseLine } from "../types";
import "./purchase-dialog.css";

/** 只读采购详情：概要与原始行分区展示，数值沿用后端口径。 */
export function PurchaseDialog({ line, onClose }: { line: PurchaseLine; onClose: () => void }) {
  const fields = [
    ["子采购单", line.child],
    ["母采购单", line.parent],
    ["供应商", line.supplier],
    ["采购品名", line.name],
    ["规格型号", line.model],
    ["采购币种", line.currency],
    [line.scope === "order" ? "子单数量" : "本次数量", line.quantity],
    ["单位", line.unit],
    ["采购含税单价", line.price],
    [line.scope === "order" ? "订单含税金额（未分摊）" : "本次采购含税金额", line.amount],
    ["销售订单汇率", line.salesOrderExchangeRate],
  ];
  return (
    <Dialog title="子采购明细" onClose={onClose} className="fr-purchase-dialog">
      <div className="fr-purchase-dialog__body">
        <p className="fr-purchase-dialog__hint">审核在所属报关单统一进行。</p>
        <dl className="fr-purchase-dialog__fields">
          {fields.map(([label, value]) => (
            <div key={label}>
              <dt>{label}</dt>
              <dd>{value || "来源未提供"}</dd>
            </div>
          ))}
          <div className="fr-purchase-dialog__note">
            <dt>来源说明</dt>
            <dd>{line.note || "来源未提供"}</dd>
          </div>
        </dl>
        {Boolean(line.members?.length) && (
          <section className="fr-purchase-dialog__lines" aria-label="子采购订单原始行">
            <SectionTitle title="合并前采购明细" />
            <DataTable
              label="合并前采购明细"
              rows={line.members ?? []}
              rowKey={(member) => member.id}
              density="compact"
              minWidth={720}
              maxHeight="min(360px, 40dvh)"
              columns={[
                {
                  key: "name",
                  header: "采购品名",
                  width: "22%",
                  render: (member) => member.name || "未提供",
                },
                { key: "model", header: "规格型号", width: "20%", render: (member) => member.model || "—" },
                {
                  key: "quantity",
                  header: "原始数量",
                  width: "15%",
                  align: "right",
                  render: (member) => member.quantity || "未提供",
                },
                { key: "unit", header: "单位", width: "9%", render: (member) => member.unit || "未提供" },
                {
                  key: "price",
                  header: "原含税单价",
                  width: "16%",
                  align: "right",
                  render: (member) => member.price || "未提供",
                },
                {
                  key: "amount",
                  header: "原含税金额",
                  width: "18%",
                  align: "right",
                  render: (member) => member.amount || "未提供",
                },
              ]}
            />
          </section>
        )}
      </div>
    </Dialog>
  );
}
