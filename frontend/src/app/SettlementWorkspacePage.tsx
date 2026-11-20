import { SettlementHkReceiptPage } from "../modules/settlement/pages/SettlementHkReceiptPage";
import { useCallback, useState } from "react";
import { DirectDocumentGroupWorkspace } from "../modules/settlement/components/DirectDocumentGroupWorkspace";
import { DirectDocumentMergeWorkspace } from "../modules/settlement/components/DirectDocumentMergeWorkspace";
import { DeclarationDetailHost } from "../modules/settlement/components/DeclarationDetailDrawer";
import { Link, useLocation, useParams } from "react-router";
import { SettlementBankReceiptsPage } from "../modules/settlement/pages/SettlementBankReceiptsPage";
import { SettlementHkTransitPage } from "../modules/settlement/pages/SettlementHkTransitPage";
import { SettlementDeclarationsPage } from "../modules/settlement/pages/SettlementDeclarationsPage";
import { SettlementLedgerPage } from "../modules/settlement/pages/SettlementLedgerPage";
import { SettlementOverviewPage } from "../modules/settlement/pages/SettlementOverviewPage";
import { SettlementPartiesPage } from "../modules/settlement/pages/SettlementPartiesPage";
import { AppFrame } from "./WorkspaceFrame";
import { navigation } from "./navigation";
import { paths, settlementDirectDocumentsPath, type SubView } from "./paths";
import { useViewNavigate } from "./useViewNavigate";

const PAGES = {
  overview: {
    child: "settlement-overview",
    title: "收汇总览",
    description: "统一查看香港中转与直接收汇的报关应收、客户实收和未收金额；香港汇回境内单独跟踪。",
    source: "海关回执 + 香港到账登记 + 银行收汇明细",
  },
  declarations: {
    child: "settlement-declarations",
    title: "报关应收汇",
    description: "按海关回执查看应收汇与回款路径；香港回款在香港中转批次登记，非香港中转进入直接收汇明细。",
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
    title: "香港中转",
    description: "贸易国为香港：香港账户收款 → 提单与销售合同齐全后出资料包 → 汇回境内，汇回对平后结汇。",
    source: "银行水单登记（香港到账、境内汇回）",
  },
  "hk-register": {
    child: "settlement-hk",
    title: "登记香港回款",
    description: "将已选报关单登记到同一条香港到账流水，金额对平后提交并建立批次。",
    source: "银行水单 + 海关回执",
  },
  direct: {
    child: "settlement-direct",
    title: "直接收汇明细",
    description:
      "非香港中转的境外收货人总账：出口取自报关单，收汇取自银行收汇明细，按境外收货人和收款人汇总差额。",
    source: "海关回执 + 银行收汇明细",
  },
  "direct-group": {
    child: "settlement-direct",
    title: "直接收汇资料组",
    description: "在资料组统一上传提单、生成销售合同；报关单详情只读展示资料。",
    source: "海关回执 + 提单与销售合同",
  },
  "direct-merge": {
    child: "settlement-direct",
    title: "合并办理资料",
    description: "一张提单覆盖多票直接收汇报关单时，将单票资料组合并办理。",
    source: "当前报关依据 + 已有资料",
  },
  parties: {
    child: "settlement-parties",
    title: "合同抬头",
    description: "销售合同买卖双方的中英文名称、地址、电话与印章。买方名称须与海关回执的境外收货人一致。",
    source: "人工维护",
  },
} as const satisfies Record<string, { child: SubView; title: string; description: string; source: string }>;

const KEYS: Record<string, keyof typeof PAGES> = {
  [paths.settlementOverview]: "overview",
  [paths.settlementBank]: "bank",
  [paths.settlementHk]: "hk",
  [paths.settlementHkRegister]: "hk-register",
  [paths.settlementDirect]: "direct",
  [paths.settlementParties]: "parties",
};

/** 结汇对账：各子页面共用一个页面权限，由侧栏子列表切换。 */
export default function SettlementWorkspacePage() {
  const { pathname, search } = useLocation();
  const navigateView = useViewNavigate();
  const { groupId } = useParams();
  const [groupHeading, setGroupHeading] = useState({ id: 0, label: "" });
  const loadedGroup = useCallback(
    (id: number, label: string) =>
      setGroupHeading((current) => (current.id === id && current.label === label ? current : { id, label })),
    [],
  );
  const key =
    pathname === paths.settlementDocumentMerge
      ? "direct-merge"
      : groupId
        ? "direct-group"
        : (KEYS[pathname] ?? "declarations");
  const current = PAGES[key];
  return (
    <AppFrame
      groups={navigation}
      activeId="settlement"
      activeChildId={current.child}
      onNavigate={navigateView}
      title={
        key === "direct-group" && groupHeading.id === Number(groupId)
          ? `资料组 ${groupHeading.label}`
          : current.title
      }
      breadcrumb={
        key === "hk-register" ? (
          <Link to={paths.settlementHk}>香港中转</Link>
        ) : key === "direct-group" || key === "direct-merge" ? (
          <Link to={settlementDirectDocumentsPath()}>直接收汇明细</Link>
        ) : key === "overview" ? (
          <span>结汇对账</span>
        ) : (
          <Link to={paths.settlementOverview}>结汇对账</Link>
        )
      }
      description={current.description}
      meta={[{ label: "数据来源", value: current.source }]}
    >
      <DeclarationDetailHost />
      {key === "overview" && <SettlementOverviewPage />}
      {key === "declarations" && <SettlementDeclarationsPage />}
      {key === "bank" && <SettlementBankReceiptsPage />}
      {key === "hk" && <SettlementHkTransitPage />}
      {key === "hk-register" && <SettlementHkReceiptPage />}
      {key === "direct" && <SettlementLedgerPage key={new URLSearchParams(search).get("consignee") || ""} />}
      {key === "direct-group" && (
        <DirectDocumentGroupWorkspace key={groupId} id={Number(groupId)} onLoaded={loadedGroup} />
      )}
      {key === "direct-merge" && (
        <DirectDocumentMergeWorkspace
          key={new URLSearchParams(search).get("declarationNo") || ""}
          source={new URLSearchParams(search).get("declarationNo") || ""}
        />
      )}
      {key === "parties" && <SettlementPartiesPage />}
    </AppFrame>
  );
}
