import { Link, Navigate, useParams, useSearchParams } from "react-router";
import { MatchingInvoicePage } from "../modules/matching/pages/MatchingInvoicePage";
import { MatchingQueuePage } from "../modules/matching/pages/MatchingQueuePage";
import { AppFrame } from "./WorkspaceFrame";
import { navigation } from "./navigation";
import { matchingInvoicePath, paths } from "./paths";
import { useViewNavigate } from "./useViewNavigate";

export default function MatchingWorkspacePage() {
  const navigateView = useViewNavigate();
  const { invoiceId } = useParams();
  const [search] = useSearchParams();
  // 旧地址 /matching?invoiceId=… 跳转到 /matching/…，保留一个版本后删除。
  const legacy = search.get("invoiceId");
  if (!invoiceId && legacy) return <Navigate to={matchingInvoicePath(legacy)} replace />;
  return (
    <AppFrame
      groups={navigation}
      activeId="match"
      onNavigate={navigateView}
      title={invoiceId ? "发票比对" : "比对审核队列"}
      description="把进项发票行与已审核的子采购行逐项对照，通过后自动更新开票任务的收票进度"
      breadcrumb={invoiceId ? <Link to={paths.matching}>比对审核队列</Link> : undefined}
    >
      {invoiceId ? <MatchingInvoicePage key={invoiceId} invoiceId={invoiceId} /> : <MatchingQueuePage />}
    </AppFrame>
  );
}
