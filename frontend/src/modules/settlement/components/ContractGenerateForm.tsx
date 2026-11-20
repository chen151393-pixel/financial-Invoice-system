import { Link } from "react-router";
import { paths } from "../../../app/paths";
import { Button, DataTable } from "../../../shared/components/ui";
import type { BatchDocuments, GenerateContractsBody } from "../types";

/** 合同双方取关联报关单，经办人确认条款；金额、日期、口岸由后端按海关回执和提单取数。 */
export function ContractGenerateForm({
  documents,
  busy,
  onCancel,
  onSubmit,
}: {
  documents: BatchDocuments;
  busy: boolean;
  onCancel: () => void;
  onSubmit: (body: GenerateContractsBody) => void;
}) {
  const { defaults } = documents;
  return (
    <form
      className="settlement-form"
      aria-label="生成销售合同"
      onSubmit={(event) => {
        event.preventDefault();
        const data = new FormData(event.currentTarget);
        const value = (name: string) => String(data.get(name) || "").trim();
        onSubmit({
          tradeTerm: value("tradeTerm"),
          paymentTermsCn: value("paymentTermsCn"),
          paymentTermsEn: value("paymentTermsEn"),
        });
      }}
    >
      <p className="settlement-form__hint">
        买方取对应报关单的境外收货人，卖方取 NS 报关单的申报抬头；系统自动匹配，不能在此改选。地址和印章在
        <Link to={paths.settlementParties}>合同抬头</Link>中维护。
      </p>
      <div className="settlement-form__wide">
        <DataTable
          label="合同买卖方"
          columns={[
            {
              key: "contract",
              header: "销售订单 / 对应报关单",
              render: (row) => (
                <div className="settlement-cell">
                  <strong>{row.contractNo}</strong>
                  <span>{row.declarationNos.join("、")}</span>
                </div>
              ),
            },
            { key: "buyer", header: "买方（境外收货人）", render: (row) => row.buyerName || "待核对" },
            { key: "seller", header: "卖方（NS 申报抬头）", render: (row) => row.sellerName || "待核对" },
          ]}
          rows={documents.planned}
          rowKey={(row) => row.key || row.contractNo}
          density="compact"
          minWidth={640}
        />
      </div>
      <label>
        成交方式
        <input name="tradeTerm" required maxLength={20} defaultValue={defaults.tradeTerm} />
      </label>
      <label className="settlement-form__wide">
        付款条件（中文）
        <input name="paymentTermsCn" required maxLength={300} defaultValue={defaults.paymentTermsCn} />
      </label>
      <label className="settlement-form__wide">
        付款条件（英文）
        <input name="paymentTermsEn" required maxLength={300} defaultValue={defaults.paymentTermsEn} />
      </label>
      <div className="settlement-form__actions">
        <Button type="button" variant="ghost" onClick={onCancel} disabled={busy}>
          取消
        </Button>
        <Button type="submit" variant="primary" disabled={busy}>
          {busy ? "正在生成…" : "生成销售合同"}
        </Button>
      </div>
    </form>
  );
}
