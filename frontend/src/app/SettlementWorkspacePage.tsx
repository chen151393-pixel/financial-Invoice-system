import { lazy, Suspense, useCallback, useState } from "react";
import { Skeleton } from "../shared/components/ui";
import { Link, useLocation, useParams } from "react-router";
import { AppFrame } from "./WorkspaceFrame";
import { navigation } from "./navigation";
import { paths, settlementDirectDocumentsPath, type SubView } from "./paths";
import { useViewNavigate } from "./useViewNavigate";

const DeclarationDetailHost = lazy(() =>
  import("../modules/settlement/components/DeclarationDetailDrawer").then((m) => ({
    default: m.DeclarationDetailHost,
  })),
);
const DirectDocumentGroupWorkspace = lazy(() =>
  import("../modules/settlement/components/DirectDocumentGroupWorkspace").then((m) => ({
    default: m.DirectDocumentGroupWorkspace,
  })),
);
const DirectDocumentMergeWorkspace = lazy(() =>
  import("../modules/settlement/components/DirectDocumentMergeWorkspace").then((m) => ({
    default: m.DirectDocumentMergeWorkspace,
  })),
);
const SettlementHkReceiptPage = lazy(() =>
  import("../modules/settlement/pages/SettlementHkReceiptPage").then((m) => ({
    default: m.SettlementHkReceiptPage,
  })),
);
const SettlementHkBatchPage = lazy(() =>
  import("../modules/settlement/pages/SettlementHkBatchPage").then((m) => ({
    default: m.SettlementHkBatchPage,
  })),
);
const SettlementBankReceiptsPage = lazy(() =>
  import("../modules/settlement/pages/SettlementBankReceiptsPage").then((m) => ({
    default: m.SettlementBankReceiptsPage,
  })),
);
const SettlementHkTransitPage = lazy(() =>
  import("../modules/settlement/pages/SettlementHkTransitPage").then((m) => ({
    default: m.SettlementHkTransitPage,
  })),
);
const SettlementDeclarationsPage = lazy(() =>
  import("../modules/settlement/pages/SettlementDeclarationsPage").then((m) => ({
    default: m.SettlementDeclarationsPage,
  })),
);
const SettlementLedgerPage = lazy(() =>
  import("../modules/settlement/pages/SettlementLedgerPage").then((m) => ({
    default: m.SettlementLedgerPage,
  })),
);
const SettlementOverviewPage = lazy(() =>
  import("../modules/settlement/pages/SettlementOverviewPage").then((m) => ({
    default: m.SettlementOverviewPage,
  })),
);
const SettlementPartiesPage = lazy(() =>
  import("../modules/settlement/pages/SettlementPartiesPage").then((m) => ({
    default: m.SettlementPartiesPage,
  })),
);

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
  "hk-batch": {
    child: "settlement-hk",
    title: "香港批次资料",
    description: "集中办理本批次提单、销售合同与资料包，并跟踪资料出具和汇回结汇。",
    source: "香港到账登记 + 海关回执 + 提单与销售合同",
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
  const { pathname, search, state } = useLocation();
  const navigateView = useViewNavigate();
  const { groupId, batchId } = useParams();
  const hkReturnTo = (state as { hkReturnTo?: string } | null)?.hkReturnTo;
  const hkBack =
    hkReturnTo === paths.settlementHk || hkReturnTo?.startsWith(`${paths.settlementHk}?`)
      ? hkReturnTo
      : paths.settlementHk;
  const [groupHeading, setGroupHeading] = useState({ id: 0, label: "" });
  const loadedGroup = useCallback(
    (id: number, label: string) =>
      setGroupHeading((current) => (current.id === id && current.label === label ? current : { id, label })),
    [],
  );
  const key =
    pathname === paths.settlementDocumentMerge
      ? "direct-merge"
      : batchId
        ? "hk-batch"
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
        key === "hk-batch" ? (
          <Link to={hkBack}>香港中转批次</Link>
        ) : key === "hk-register" ? (
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
      <Suspense fallback={<Skeleton rows={5} label="正在加载页面…" />}>
        <DeclarationDetailHost />
        {key === "overview" && <SettlementOverviewPage />}
        {key === "declarations" && <SettlementDeclarationsPage />}
        {key === "bank" && <SettlementBankReceiptsPage />}
        {key === "hk" && <SettlementHkTransitPage />}
        {key === "hk-register" && <SettlementHkReceiptPage />}
        {key === "hk-batch" && <SettlementHkBatchPage key={batchId} batchId={Number(batchId)} />}
        {key === "direct" && (
          <SettlementLedgerPage key={new URLSearchParams(search).get("consignee") || ""} />
        )}
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
      </Suspense>
    </AppFrame>
  );
}
