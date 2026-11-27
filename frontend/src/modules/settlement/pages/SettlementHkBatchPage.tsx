import { useLocation, useSearchParams } from "react-router";
import { BatchWorkspace, type BatchSection } from "../components/BatchWorkspace";
import "../components/settlement.css";

/** 页签保存在地址中；原列表范围通过页面外壳的路由状态返回。 */
export function SettlementHkBatchPage({ batchId }: { batchId: number }) {
  const [params, setParams] = useSearchParams();
  const location = useLocation();
  function changeSection(section: BatchSection) {
    const next = new URLSearchParams(params);
    if (section === "remit") next.set("mode", "remit");
    else next.delete("mode");
    setParams(next, { replace: true, state: location.state });
  }
  return (
    <BatchWorkspace
      batchId={batchId}
      section={params.get("mode") === "remit" ? "remit" : "documents"}
      onSectionChange={changeSection}
    />
  );
}
