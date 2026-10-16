import { useState } from "react";
import { Button } from "../../../shared/components/Button";
import type { TaskLine, ClosureRequest } from "../types/task";
export function DifferenceClosure({
  line,
  busy,
  onClose,
}: {
  line: TaskLine;
  busy: boolean;
  onClose: (lineId: string, body: ClosureRequest) => Promise<boolean>;
}) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [requestId] = useState(() => crypto.randomUUID());
  return (
    <div className="it-closure">
      {!open ? (
        <Button
          disabled={busy || !line.close.allowed}
          title={line.close.reason}
          onClick={() => setOpen(true)}
        >
          按差异结束
        </Button>
      ) : (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void onClose(line.id, {
              requestId,
              purchaseBasisId: line.purchaseBasisId ?? "",
              ledgerSha256: line.ledgerSha256 ?? "",
              reason,
            }).then((saved) => saved && setOpen(false));
          }}
        >
          <label>
            差异结束说明
            <textarea rows={2} disabled={busy} value={reason} onChange={(e) => setReason(e.target.value)} />
          </label>
          <p className="it-help">仅对当前审核依据和分配记录生效。后续分配、撤销或换版后需重新判断。</p>
          <Button type="submit" disabled={busy} variant="primary">
            {busy ? "保存中…" : "登记差异结束"}
          </Button>
          <Button disabled={busy} onClick={() => setOpen(false)}>
            取消
          </Button>
        </form>
      )}
      {!line.close.allowed && <p className="it-help">{line.close.reason}</p>}
    </div>
  );
}
