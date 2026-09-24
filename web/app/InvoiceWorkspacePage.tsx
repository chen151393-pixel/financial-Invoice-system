import { useEffect } from "react";
import { InvoiceList } from "../modules/invoice/InvoiceList";
import { AppFrame } from "../shared/components/AppFrame";
import { navigation } from "./navigation";
import { viewPath } from "./views";

export default function InvoiceWorkspacePage() {
  useEffect(() => {
    if (location.pathname !== "/invoices") history.replaceState(null, "", "/invoices");
  }, []);
  return (
    <AppFrame
      groups={navigation}
      activeId="invoices"
      onNavigate={(target) => location.assign(viewPath(target))}
      title="进项发票"
      subtitle="查询已导入数据库的发票与票面商品明细"
      mode="live"
      dataLabel="真实数据库 · 当前身份"
      notice={null}
      actions={
        <a className="ui-button ui-button--primary" href="/sync/lemon">
          导入发票
        </a>
      }
    >
      <InvoiceList />
    </AppFrame>
  );
}
