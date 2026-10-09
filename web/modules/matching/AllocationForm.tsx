import { useRef, useState } from "react";
import { Button } from "../../shared/components/Button";
import { confirmMatching, type ConfirmMatching, type MatchingPreview } from "./api";

export function AllocationForm({
  invoiceId,
  snapshot,
  candidate,
  busy,
  onBusy,
  onSaved,
}: {
  invoiceId: string;
  snapshot: string;
  candidate: MatchingPreview["candidates"][number];
  busy: boolean;
  onBusy: (value: boolean) => void;
  onSaved: (message: string) => void;
}) {
  const [quantity, setQuantity] = useState(candidate.suggestedQuantity);
  const [error, setError] = useState("");
  const [pending, setPending] = useState<ConfirmMatching | null>(null);
  const sending = useRef(false);
  const inputId = `allocate-${candidate.invoiceLineId}-${candidate.purchaseLineId}`;
  return (
    <form
      className="matching-workspace__allocation"
      onSubmit={(event) => {
        event.preventDefault();
        if (sending.current) return;
        sending.current = true;
        const body = pending ?? {
          requestId: crypto.randomUUID(),
          snapshot,
          quantity,
          invoiceLineId: candidate.invoiceLineId,
          purchaseLineId: candidate.purchaseLineId,
        };
        setPending(body);
        onBusy(true);
        setError("");
        void confirmMatching(invoiceId, body)
          .then((result) => {
            setPending(null);
            onSaved(`${result.message}，数量 ${result.quantity}，含税金额 ${result.gross}`);
          })
          .catch((reason: unknown) => {
            setError(reason instanceof Error ? reason.message : "保存失败，请刷新核实已确认记录");
          })
          .finally(() => {
            sending.current = false;
            onBusy(false);
          });
      }}
    >
      <p>{candidate.reason}</p>
      <p>
        发票剩余数量 {candidate.invoiceRemaining}；采购剩余数量 {candidate.purchaseRemaining}
      </p>
      <label htmlFor={inputId}>本次分配数量</label>
      <input
        id={inputId}
        inputMode="decimal"
        value={quantity}
        disabled={busy || !candidate.allowed || pending !== null}
        onChange={(event) => setQuantity(event.target.value)}
      />
      <Button type="submit" disabled={busy || !candidate.allowed}>
        {busy ? "正在保存…" : pending ? "重试本次确认" : "确认本次分配"}
      </Button>
      {error && <p role="alert">{error}。如需修改数量，请先刷新候选并核实已确认记录。</p>}
    </form>
  );
}
