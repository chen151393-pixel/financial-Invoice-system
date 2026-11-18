import { Link, useLocation } from "react-router";
import { SettlementBankReceiptsPage } from "../modules/settlement/pages/SettlementBankReceiptsPage";
import { SettlementBatchesPage } from "../modules/settlement/pages/SettlementBatchesPage";
import { SettlementDeclarationsPage } from "../modules/settlement/pages/SettlementDeclarationsPage";
import { SettlementLedgerPage } from "../modules/settlement/pages/SettlementLedgerPage";
import { SettlementPartiesPage } from "../modules/settlement/pages/SettlementPartiesPage";
import { AppFrame } from "./WorkspaceFrame";
import { navigation } from "./navigation";
import { paths, type SubView } from "./paths";
import { useViewNavigate } from "./useViewNavigate";

const PAGES = {
  declarations: {
    child: "settlement-declarations",
    title: "报关应收汇",
    description: "按海关回执汇总应收汇并判定回款路径：香港中转登记回款建批次，非香港中转进直接收汇明细。",
    source: "海关回执（出口日期、成交总价）",
  },
  bank: {
    child: "settlement-bank",
    title: "银行收汇明细",
    description: "境内美金账户的收汇记录，按银行流水表格导入；实际客户取表格中填写的境外收货人。",
    source: "银行流水表格导入",
  },
  hk: {
    child: "settlement-hk",
    title: "香港中转批次",
    description: "贸易国为香港：香港账户收款 → 提单与销售合同齐全后出资料包 → 汇回境内，汇回对平后结汇。",
    source: "银行水单登记（香港到账、境内汇回）",
  },
  direct: {
    child: "settlement-direct",
    title: "直接收汇明细",
    description: "非香港中转的境外收货人总账：出口取自报关单，收汇取自银行收汇明细，按日期逐笔累计期末余额。",
    source: "海关回执 + 银行收汇明细",
  },
  parties: {
    child: "settlement-parties",
    title: "合同抬头",
    description: "销售合同买卖双方的中英文名称、地址、电话与印章。买方名称须与海关回执的境外收货人一致。",
    source: "人工维护",
  },
} as const satisfies Record<string, { child: SubView; title: string; description: string; source: string }>;

const KEYS: Record<string, keyof typeof PAGES> = {
  [paths.settlementBank]: "bank",
  [paths.settlementHk]: "hk",
  [paths.settlementDirect]: "direct",
  [paths.settlementParties]: "parties",
};

/** 结汇对账：各子页面共用一个页面权限，由侧栏子列表切换。 */
export default function SettlementWorkspacePage() {
  const { pathname } = useLocation();
  const navigateView = useViewNavigate();
  const key = KEYS[pathname] ?? "declarations";
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
      {key === "declarations" && <SettlementDeclarationsPage />}
      {key === "bank" && <SettlementBankReceiptsPage />}
      {key === "hk" && <SettlementBatchesPage route="hk_transit" />}
      {key === "direct" && <SettlementLedgerPage />}
      {key === "parties" && <SettlementPartiesPage />}
    </AppFrame>
  );
}
