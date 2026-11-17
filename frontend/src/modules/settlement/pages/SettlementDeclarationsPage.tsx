import { useState } from "react";
import { BatchDetailDialog } from "../components/BatchDetailDialog";
import { CandidatePanel } from "../components/CandidatePanel";
import "../components/settlement.css";

/** 待结汇报关单：勾选报关单登记回款；建好的批次立即打开详情，之后在对应路径的批次页跟进。 */
export function SettlementDeclarationsPage() {
  const [open, setOpen] = useState<number | null>(null);
  return (
    <div className="settlement-page">
      <CandidatePanel onCreated={setOpen} />
      {open !== null && (
        <BatchDetailDialog batchId={open} onClose={() => setOpen(null)} onChanged={() => undefined} />
      )}
    </div>
  );
}
