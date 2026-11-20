import { ReceivablePanel } from "../components/ReceivablePanel";
import "../components/settlement.css";

/** 报关应收汇：按客户汇总与报关单明细，只读；登记回款、办资料、核对总账在各自页面办理。 */
export function SettlementDeclarationsPage() {
  return (
    <div className="settlement-page">
      <ReceivablePanel />
    </div>
  );
}
