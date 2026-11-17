import { Link, useLocation } from "react-router";
import { SettlementBatchesPage } from "../modules/settlement/pages/SettlementBatchesPage";
import { SettlementDeclarationsPage } from "../modules/settlement/pages/SettlementDeclarationsPage";
import { SettlementPartiesPage } from "../modules/settlement/pages/SettlementPartiesPage";
import { AppFrame } from "./WorkspaceFrame";
import { navigation } from "./navigation";
import { paths, type SubView } from "./paths";
import { useViewNavigate } from "./useViewNavigate";

const PAGES = {
  declarations: {
    child: "settlement-declarations",
    title: "待结汇报关单",
    description: "已匹配海关回执、尚未结汇的报关单。勾选报关单并登记一笔回款即建结汇批次；差额只认手续费。",
    source: "海关回执成交总价",
  },
  hk: {
    child: "settlement-hk",
    title: "香港中转批次",
    description: "贸易国为香港：香港账户收款 → 提单与销售合同齐全后出资料包 → 汇回境内，汇回对平后结汇。",
    source: "银行水单登记（香港到账、境内汇回）",
  },
  direct: {
    child: "settlement-direct",
    title: "直接收汇批次",
    description: "贸易国为客户国家：货款直接付到境内账户，到账对平后结汇。",
    source: "银行水单登记（境内到账）",
  },
  parties: {
    child: "settlement-parties",
    title: "合同抬头",
    description: "销售合同买卖双方的中英文名称、地址、电话与印章。买方名称须与海关回执的境外收货人一致。",
    source: "人工维护",
  },
} as const satisfies Record<string, { child: SubView; title: string; description: string; source: string }>;

/** 结汇对账：三个子页面共用一个页面权限，由侧栏子列表切换。 */
export default function SettlementWorkspacePage() {
  const { pathname } = useLocation();
  const navigateView = useViewNavigate();
  const key =
    pathname === paths.settlementHk
      ? "hk"
      : pathname === paths.settlementDirect
        ? "direct"
        : pathname === paths.settlementParties
          ? "parties"
          : "declarations";
  const current = PAGES[key];
  return (
    <AppFrame
      groups={navigation}
      activeId="settlement"
      activeChildId={current.child}
      onNavigate={navigateView}
      title={current.title}
      breadcrumb={
        key === "declarations" ? <span>结汇对账</span> : <Link to={paths.settlement}>结汇对账</Link>
      }
      description={current.description}
      meta={[{ label: "数据来源", value: current.source }]}
    >
      {key === "declarations" ? (
        <SettlementDeclarationsPage />
      ) : key === "parties" ? (
        <SettlementPartiesPage />
      ) : (
        <SettlementBatchesPage key={key} route={key === "hk" ? "hk_transit" : "direct"} />
      )}
    </AppFrame>
  );
}
