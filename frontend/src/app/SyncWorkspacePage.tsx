import { Link, useLocation } from "react-router";
import SyncPage from "../modules/sync/SyncPage";
import { AppFrame } from "./WorkspaceFrame";
import { navigation } from "./navigation";
import { paths } from "./paths";
import { useViewNavigate } from "./useViewNavigate";
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
            : "绑定已有柠檬云账号，或导入进项发票文件。"
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
      dataLabel={source === "lemon" ? "文件导入 · 本地保存" : undefined}
      notice={
        source === "ns"
          ? "不修改 NS 源单据；子采购订单、报关单支持按页拉取并保存到 MySQL，暂不支持定时同步。"
          : source === "lemon"
            ? "支持已有账号授权绑定与 Excel 导入；发票自动拉取和附件同步尚未接入。导入后自动生成比对建议，需人工审核，不写回 NS。"
            : "NS 支持按页读取，子采购订单及报关单支持保存到 MySQL；柠檬云支持账号绑定与文件导入，定时同步待接入。"
      }
    >
      <SyncPage source={source}>
        {source === "lemon" && (
          <>
            <LemonBindingPanel />
            <div id="lemon-invoice-import" tabIndex={-1}>
              <InvoiceImportPage />
            </div>
          </>
        )}
      </SyncPage>
    </AppFrame>
  );
}
