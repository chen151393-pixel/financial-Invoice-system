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
      subtitle="发票行与已审核子采购行逐项比对，人工通过后更新开票任务收票进度"
      mode="live"
      dataLabel="已导入发票 · 已审核子采购"
      notice="系统生成带置信度的建议，全部需要人工审核；不一致只降低置信度。币种待核实、作废红冲、超出发票行等情况不能通过。不写回 NS。"
      actions={
        <div className="matching-row">
          {invoiceId && (
            <Link className="ui-button" to={paths.matching}>
              审核队列
            </Link>
          )}
          <Link className="ui-button" to={paths.invoices}>
            进项发票
          </Link>
          <Link className="ui-button" to={paths.tasks}>
            开票跟进
          </Link>
        </div>
      }
    >
      {invoiceId ? <MatchingInvoicePage key={invoiceId} invoiceId={invoiceId} /> : <MatchingQueuePage />}
    </AppFrame>
  );
}
