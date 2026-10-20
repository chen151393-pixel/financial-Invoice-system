import { Link } from "react-router";
import { InvoiceListPage } from "../modules/invoice/pages/InvoiceListPage";
import { AppFrame } from "./WorkspaceFrame";
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
