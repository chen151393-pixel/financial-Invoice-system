import { useState } from "react";
import { useSearchParams } from "react-router";
import { Tabs } from "../../../shared/components/ui";
import { CandidatePanel } from "../components/CandidatePanel";
import { BatchDetailDialog } from "../components/BatchDetailDialog";
import { SettlementBatchesPage } from "./SettlementBatchesPage";

const VIEWS = [
  { key: "receipts", label: "待登记回款" },
  { key: "batches", label: "已建批次" },
] as const;

/** 香港中转的回款登记、资料与汇回统一在此处理；URL 保留页签和客户范围。 */
export function SettlementHkTransitPage() {
  const [params, setParams] = useSearchParams();
  const view = params.get("tab") === "receipts" ? "receipts" : "batches";
  const [created, setCreated] = useState<number | null>(null);
  function changeView(next: "receipts" | "batches") {
    const values = new URLSearchParams(params);
    if (next === "receipts") values.set("tab", next);
    else values.delete("tab");
    setParams(values);
  }
  return (
    <div className="settlement-page">
      <Tabs label="香港中转工作区" items={VIEWS} value={view} onChange={changeView} />
      {view === "receipts" ? (
        <CandidatePanel consignee={params.get("consignee") || ""} onCreated={setCreated} />
      ) : (
        <SettlementBatchesPage route="hk_transit" />
      )}
      {created !== null && (
        <BatchDetailDialog
          batchId={created}
          onClose={() => {
            setCreated(null);
            changeView("batches");
          }}
          onChanged={() => undefined}
        />
      )}
    </div>
  );
}
