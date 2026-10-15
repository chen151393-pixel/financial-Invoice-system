import { Link } from "react-router";
import { InvoiceListPage } from "../modules/invoice/pages/InvoiceListPage";
import { AppFrame } from "../shared/components/AppFrame";
import { navigation } from "./navigation";
import { paths } from "./paths";
import { useViewNavigate } from "./useViewNavigate";

export default function InvoiceWorkspacePage() {
  const navigateView = useViewNavigate();
  return (
    <AppFrame
      groups={navigation}
      activeId="invoices"
      onNavigate={navigateView}
      title="进项发票"
      subtitle="查询已导入数据库的发票与票面商品明细"
      mode="live"
      dataLabel="已导入的进项发票"
      notice={null}
      actions={
        <Link className="ui-button ui-button--primary" to={paths.syncLemon}>
          导入发票
        </Link>
      }
    >
      <InvoiceListPage />
    </AppFrame>
  );
}
