import { Link, useLocation } from "react-router";
import SyncPage from "../modules/sync/SyncPage";
import { AppFrame } from "./WorkspaceFrame";
import { navigation } from "./navigation";
import { paths } from "./paths";
import { useViewNavigate } from "./useViewNavigate";
import { LemonInvoicePanel } from "../modules/sync/LemonInvoicePanel";
import { LemonBindingPanel } from "../modules/sync/LemonBindingPanel";
import { InvoiceImportPage } from "../modules/invoice/pages/InvoiceImportPage";

export default function SyncWorkspacePage() {
  const { pathname } = useLocation();
  const navigateView = useViewNavigate();
  const source = pathname === paths.syncNs ? "ns" : pathname === paths.syncLemon ? "lemon" : "overview";
  return (
    <AppFrame
      groups={navigation}
      activeId="sync"
      onNavigate={navigateView}
      title={source === "ns" ? "NS 数据同步" : source === "lemon" ? "柠檬云数据同步" : "数据同步中心"}
      subtitle={
        source === "overview"
          ? "监控 NetSuite 与柠檬云的数据新鲜度、批次和失败任务"
          : source === "ns"
            ? "选择采购订单、子采购订单或报关单，按需拉取 NS 单据。"
            : "绑定账号并选择账套，手动拉取进项发票或导入文件。"
      }
      actions={
        source === "overview" ? (
          <div className="sync-overview__actions">
            <Link className="ui-button ui-button--secondary" to={paths.syncNs}>
              查看同步状态
            </Link>
            <a className="ui-button ui-button--primary" href="#sync-platforms">
              选择平台同步
            </a>
          </div>
        ) : undefined
      }
      mode={source === "overview" ? "pending" : "live"}
      dataLabel={source === "lemon" ? "API 拉取 / 文件导入 · 本地保存" : undefined}
      notice={
        source === "ns"
          ? "不修改 NS 源单据；子采购订单、报关单支持按页拉取并保存到 MySQL，暂不支持定时同步。"
          : source === "lemon"
            ? "支持专业版发票与商品明细拉取、列表单张或批量补拉及 Excel 导入。明细完整后生成待审核比对建议，不写回 NS。"
            : "NS 支持按页读取，子采购订单及报关单支持保存到 MySQL；柠檬云支持手动拉票与文件导入，定时同步待接入。"
      }
    >
      <SyncPage source={source}>
        {source === "lemon" && (
          <>
            <LemonBindingPanel />
            <LemonInvoicePanel />
            <div id="lemon-invoice-import" tabIndex={-1}>
              <InvoiceImportPage />
            </div>
          </>
        )}
      </SyncPage>
    </AppFrame>
  );
}
