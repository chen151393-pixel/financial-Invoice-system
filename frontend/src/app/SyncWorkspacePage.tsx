import { Link, useLocation } from "react-router";
import SyncPage from "../modules/sync/SyncPage";
import { AppFrame } from "./WorkspaceFrame";
import { navigation } from "./navigation";
import { paths } from "./paths";
import { useViewNavigate } from "./useViewNavigate";
import { LemonInvoicePanel } from "../modules/sync/LemonInvoicePanel";
import { LemonBindingPanel } from "../modules/sync/LemonBindingPanel";
import { LemonBackgroundPanel } from "../modules/sync/pages/LemonBackgroundPanel";
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
      breadcrumb={source === "overview" ? undefined : <Link to={paths.sync}>数据同步</Link>}
      actions={
        source === "overview" ? (
          <div className="sync-overview__actions">
            <Link className="ui-button ui-button--secondary" to={paths.syncNs}>
              NS 手动同步
            </Link>
            <Link className="ui-button ui-button--primary" to={paths.syncLemon}>
              配置发票同步
            </Link>
          </div>
        ) : source === "lemon" ? (
          <Link className="ui-button ui-button--secondary" to={paths.sync}>
            查看执行记录
          </Link>
        ) : undefined
      }
    >
      <SyncPage source={source}>
        {source === "lemon" && (
          <>
            <LemonBackgroundPanel />
            <section className="sync-more" aria-label="更多操作">
              <details>
                <summary>
                  <strong>账号授权与连接设置</strong>
                  <span>绑定、更换账号或刷新授权</span>
                </summary>
                <LemonBindingPanel />
              </details>
              <details>
                <summary>
                  <strong>单账套即时拉取</strong>
                  <span>选择一个账套立即读取，适合核对单个账套</span>
                </summary>
                <LemonInvoicePanel />
              </details>
              <details id="lemon-invoice-import" tabIndex={-1}>
                <summary>
                  <strong>Excel 导入</strong>
                  <span>上传柠檬云导出的 Excel 文件</span>
                </summary>
                <InvoiceImportPage />
              </details>
            </section>
          </>
        )}
      </SyncPage>
    </AppFrame>
  );
}
