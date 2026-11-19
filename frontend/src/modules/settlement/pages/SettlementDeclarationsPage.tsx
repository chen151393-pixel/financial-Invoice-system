import { CandidatePanel } from "../components/CandidatePanel";
import "../components/settlement.css";

/** 报关应收汇仅查询展示；香港回款登记在香港中转批次办理。 */
export function SettlementDeclarationsPage() {
  return (
    <div className="settlement-page">
      <CandidatePanel mode="receivables" />
    </div>
  );
}
