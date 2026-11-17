import { Link } from "react-router";
import { paths } from "../../../app/paths";
import { Button } from "../../../shared/components/ui";
import type { BatchDocuments, GenerateContractsBody } from "../types";

/** 生成销售合同前确认卖方与条款；金额、日期、口岸由后端按海关回执和提单取数。 */
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
  const { defaults, sellers } = documents;
  return (
    <form
      className="settlement-form"
      aria-label="生成销售合同"
      onSubmit={(event) => {
        event.preventDefault();
        const data = new FormData(event.currentTarget);
        const value = (name: string) => String(data.get(name) || "").trim();
        onSubmit({
          sellerPartyId: Number(value("sellerPartyId")),
          tradeTerm: value("tradeTerm"),
          paymentTermsCn: value("paymentTermsCn"),
          paymentTermsEn: value("paymentTermsEn"),
        });
      }}
    >
      <p className="settlement-form__hint">
        买方：{documents.buyerName}。按出口合同号各生成一份，金额取海关回执成交总价，口岸取提单。抬头与印章在
        <Link to={paths.settlementParties}>合同抬头</Link>中维护。
      </p>
      <label>
        卖方（境内发货人）
        <select name="sellerPartyId" required defaultValue={defaults.sellerPartyId ?? ""}>
          <option value="" disabled>
            请选择
          </option>
          {sellers.map((seller) => (
            <option key={seller.id} value={seller.id}>
              {seller.name}
              {seller.hasStamp ? "" : "（未上传印章）"}
            </option>
          ))}
        </select>
      </label>
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
