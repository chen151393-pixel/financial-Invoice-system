import { useRef, useState } from "react";
import { Alert, Button, Dialog } from "../../../shared/components/ui";
import { createBatch } from "../api";

/** 登记一笔回款：金额、手续费按银行水单填写；报关合计与差额由后端核对后在批次详情中展示。 */
export function CreateBatchDialog({
  declarationNos,
  defaultAmount,
  onClose,
  onCreated,
}: {
  declarationNos: string[];
  defaultAmount: string;
  onClose: () => void;
  onCreated: (id: number) => void;
}) {
  // 同一次弹窗内重复提交使用同一幂等号，后端返回同一批次
  const requestId = useRef(crypto.randomUUID());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(form: HTMLFormElement) {
    const data = new FormData(form);
    const value = (name: string) => String(data.get(name) || "").trim();
    setBusy(true);
    setError("");
    try {
      const batch = await createBatch({
        requestId: requestId.current,
        declarationNos,
        receivedOn: value("receivedOn"),
        receivedAmount: value("receivedAmount"),
        receivedFee: value("receivedFee") || "0",
        payer: value("payer"),
        receivingAccount: value("receivingAccount"),
        receivedReference: value("receivedReference"),
        note: value("note"),
      });
      onCreated(batch.id);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "建批次失败，请稍后重试");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog title="登记回款并建结汇批次" onClose={onClose} busy={busy}>
      <form
        className="settlement-form"
        onSubmit={(event) => {
          event.preventDefault();
          void submit(event.currentTarget);
        }}
      >
        <p className="settlement-form__hint">
          已选 {declarationNos.length} 张报关单：{declarationNos.join("、")}。 差额只认手续费：到账金额 +
          手续费须等于报关合计。
        </p>
        <label>
          到账日期
          <input name="receivedOn" type="date" required />
        </label>
        <label>
          到账金额
          <input name="receivedAmount" inputMode="decimal" required defaultValue={defaultAmount} />
        </label>
        <label>
          银行手续费
          <input name="receivedFee" inputMode="decimal" defaultValue="0" />
        </label>
        <label>
          付款方
          <input name="payer" maxLength={500} />
        </label>
        <label>
          收款账户
          <input name="receivingAccount" maxLength={200} placeholder="香港账户 / 境内账户" />
        </label>
        <label>
          流水号 / NS 收款单号
          <input name="receivedReference" maxLength={200} />
        </label>
        <label className="settlement-form__wide">
          说明
          <input name="note" maxLength={500} />
        </label>
        {error && (
          <Alert tone="danger" title="未建批次">
            {error}
          </Alert>
        )}
        <div className="settlement-form__actions">
          <Button type="button" variant="ghost" onClick={onClose} disabled={busy}>
            取消
          </Button>
          <Button type="submit" disabled={busy}>
            {busy ? "正在保存…" : "建批次"}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
