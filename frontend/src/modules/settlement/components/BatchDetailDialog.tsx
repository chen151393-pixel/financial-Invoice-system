import { useState } from "react";
import { Dialog } from "../../../shared/components/ui";
import { BatchWorkspace } from "./BatchWorkspace";
export function BatchDetailDialog({
  batchId,
  onClose,
  onChanged,
}: {
  batchId: number;
  onClose: () => void;
  onChanged: () => void;
}) {
  const [busy, setBusy] = useState(false);
  return (
    <Dialog title="结汇批次" onClose={onClose} busy={busy} className="settlement-dialog">
      <BatchWorkspace batchId={batchId} onChanged={onChanged} onBusyChange={setBusy} />
    </Dialog>
  );
}
