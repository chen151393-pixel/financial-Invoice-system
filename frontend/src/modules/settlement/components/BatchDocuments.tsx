import { useEffect, useRef, useState, type ReactNode } from "react";
import {
  Alert,
  Badge,
  Button,
  Card,
  CardContent,
  DataTable,
  ErrorState,
  EmptyState,
  CardHeader,
  Skeleton,
  type Column,
} from "../../../shared/components/ui";
import { money } from "../../../shared/format/money";
import { generateContracts, getDocuments, removeBill, updateBill, uploadBill } from "../api";
import type {
  BatchDocuments as Documents,
  DocumentTarget,
  Bill,
  Contract,
  DeclarationFile,
  PlannedContract,
} from "../types";
import { BillEditForm } from "./BillEditForm";
import { DocumentSection } from "./DocumentSection";
import { ContractGenerateForm } from "./ContractGenerateForm";

type State =
  | { kind: "loading" }
  | { kind: "ready"; documents: Documents }
  | { kind: "error"; message: string };
type ContractRow = {
  planned: PlannedContract | null;
  contract: Contract | null;
  contractNo: string;
  key: string;
};

function contractRows(documents: Documents): ContractRow[] {
  const generated = new Map(
    documents.contracts.map((contract) => [contract.key || contract.contractNo, contract]),
  );
  const rows: ContractRow[] = documents.planned.map((planned) => ({
    planned,
    contract: generated.get(planned.key || planned.contractNo) ?? null,
    contractNo: planned.contractNo,
    key: planned.key || planned.contractNo,
  }));
  const plannedNos = new Set(documents.planned.map((planned) => planned.key || planned.contractNo));
  for (const contract of documents.contracts) {
    if (!plannedNos.has(contract.key || contract.contractNo)) {
      rows.push({
        planned: null,
        contract,
        contractNo: contract.contractNo,
        key: `${contract.key || contract.contractNo}-${contract.id}`,
      });
    }
  }
  return rows;
}

/** 香港中转与直接收汇共用的资料：提单、销售合同（形式发票）、报关单、资料包。齐全度、缺项与能否操作全部来自后端。 */
export function BatchDocuments({
  target,
  onChanged,
  overview,
  standalone = false,
  revision = 0,
  actions,
  onBusyChange,
}: {
  target: DocumentTarget;
  onChanged: () => void;
  overview?: (documents: Documents) => ReactNode;
  standalone?: boolean;
  revision?: number;
  actions?: ReactNode;
  onBusyChange?: (busy: boolean) => void;
}) {
  const [state, setState] = useState<State>({ kind: "loading" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [editing, setEditing] = useState<number | null>(null);
  const [generating, setGenerating] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const fileInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const controller = new AbortController();
    getDocuments(target, controller.signal)
      .then((documents) => {
        if (!controller.signal.aborted) setState({ kind: "ready", documents });
      })
      .catch((reason: unknown) => {
        if (reason instanceof Error && reason.name === "AbortError") return;
        setState({ kind: "error", message: reason instanceof Error ? reason.message : "加载失败" });
      });
    return () => controller.abort();
  }, [target, refresh, revision]);

  async function run(action: () => Promise<Documents>) {
    setBusy(true);
    onBusyChange?.(true);
    setError("");
    try {
      setState({ kind: "ready", documents: await action() });
      setEditing(null);
      setGenerating(false);
      onChanged();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "操作失败，请稍后重试");
    } finally {
      setBusy(false);
      onBusyChange?.(false);
    }
  }

  async function uploadAll(files: File[]) {
    setBusy(true);
    onBusyChange?.(true);
    setError("");
    const failed: string[] = [];
    for (const file of files) {
      try {
        setState({ kind: "ready", documents: await uploadBill(target, file) });
      } catch (reason) {
        failed.push(`${file.name}：${reason instanceof Error ? reason.message : "上传失败"}`);
      }
    }
    if (failed.length) setError(failed.join("；"));
    setBusy(false);
    onBusyChange?.(false);
    onChanged();
  }

  if (state.kind === "loading") return <Skeleton rows={3} label="正在读取结汇资料" />;
  if (state.kind === "error") {
    return (
      <ErrorState
        title="结汇资料读取失败"
        message={state.message}
        action={<Button onClick={() => setRefresh((n) => n + 1)}>重试</Button>}
      />
    );
  }
  const documents = state.documents;
  const editable = documents.edit.allowed;
  const noticeTitle = documents.complete
    ? "提单与销售合同已齐全"
    : `资料未齐，还有 ${documents.issues.length} 项待处理`;
  const hasNoticeDetails = documents.issues.length > 0 || documents.warnings.length > 0;

  const editingBill = documents.bills.find((bill) => bill.id === editing);

  const billColumns: Column<Bill>[] = [
    {
      key: "file",
      header: "提单",
      render: (bill) => (
        <div className="settlement-cell">
          <a href={bill.fileUrl} target="_blank" rel="noreferrer">
            {bill.blNo || "（未填提单号）"}
          </a>
          <span>{bill.fileName}</span>
        </div>
      ),
    },
    {
      key: "ports",
      header: "装运口岸 → 目的口岸",
      render: (bill) => `${bill.portOfLoading || "—"} → ${bill.portOfDischarge || "—"}`,
    },
    { key: "date", header: "装船日期", render: (bill) => bill.onBoardDate || "—" },
    { key: "numbers", header: "对应报关单", render: (bill) => bill.declarationNos.join("、") },
    {
      key: "state",
      header: "状态",
      render: (bill) => (
        <div className="settlement-cell">
          {bill.missing.length ? (
            <Badge tone="warning">待补：{bill.missing.join("、")}</Badge>
          ) : bill.parseNote ? (
            <Badge tone="warning">待核对</Badge>
          ) : (
            <Badge tone="success">信息完整</Badge>
          )}
          {bill.parseNote && <span>{bill.parseNote}</span>}
        </div>
      ),
    },
    {
      key: "actions",
      header: "操作",
      render: (bill) =>
        editable ? (
          <div
            className="settlement-bill-actions"
            role="group"
            aria-label={`提单 ${bill.blNo || bill.fileName} 操作`}
          >
            <Button size="sm" disabled={busy} onClick={() => setEditing(bill.id)}>
              {bill.missing.length ? "补全信息" : bill.parseNote ? "核对信息" : "编辑信息"}
            </Button>
            <Button
              size="sm"
              variant="ghost"
              disabled={busy}
              onClick={() => {
                if (window.confirm(`移除提单 ${bill.blNo || bill.fileName}？`)) {
                  void run(() => removeBill(target, bill.id));
                }
              }}
            >
              移除
            </Button>
          </div>
        ) : (
          "—"
        ),
    },
  ];
  const declarationColumns: Column<DeclarationFile>[] = [
    {
      key: "number",
      header: "报关单",
      render: (row) => (
        <div className="settlement-cell">
          {row.declarationNo}
          {row.recordNo && <span>{row.recordNo}</span>}
        </div>
      ),
    },
    {
      key: "files",
      header: "文件",
      render: (row) => (row.fileNames.length ? row.fileNames.join("、") : "—"),
    },
    {
      key: "state",
      header: "状态",
      render: (row) => (
        <Badge tone={row.archived ? "success" : "warning"}>
          {row.archived ? "已归档，随资料包" : `${row.statusLabel}，资料包暂不含`}
        </Badge>
      ),
    },
  ];
  const contractColumns: Column<ContractRow>[] = [
    {
      key: "no",
      header: "销售订单",
      render: (row) =>
        row.contract ? (
          <a href={row.contract.fileUrl} target="_blank" rel="noreferrer">
            销售合同 {row.contractNo}
          </a>
        ) : (
          row.contractNo
        ),
    },
    {
      key: "numbers",
      header: "对应报关单",
      render: (row) => (row.planned ?? row.contract)?.declarationNos.join("、") ?? "",
    },
    {
      key: "buyer",
      header: "买方（境外收货人）",
      render: (row) => (row.contract ?? row.planned)?.buyerName || "—",
    },
    {
      key: "seller",
      header: "卖方（NS 申报抬头）",
      render: (row) => (row.contract ?? row.planned)?.sellerName || "—",
    },
    {
      key: "amount",
      header: "合同金额",
      align: "right",
      render: (row) => {
        const source = row.planned ?? row.contract;
        return source ? `${source.currency} ${money(source.amount)}` : "";
      },
    },
    {
      key: "date",
      header: "签订日期",
      render: (row) => {
        const date = (row.contract ?? row.planned)?.contractDate;
        return date ? `${date}${row.contract ? "" : "（拟）"}` : "—";
      },
    },
    {
      key: "ports",
      header: "装运口岸 → 目的口岸",
      render: (row) => {
        const source = row.contract ?? row.planned;
        return source && (source.portOfLoading || source.portOfDestination)
          ? `${source.portOfLoading || "—"} → ${source.portOfDestination || "—"}`
          : "—";
      },
    },
    {
      key: "state",
      header: "状态",
      render: (row) =>
        !row.contract ? (
          <Badge tone="warning">未生成</Badge>
        ) : row.contract.stale ? (
          <Badge tone="danger">需重新生成</Badge>
        ) : row.contract.stampNote ? (
          <Badge tone="warning">已生成 · 未盖全章</Badge>
        ) : (
          <Badge tone="success">已生成</Badge>
        ),
    },
  ];

  const billContent = (
    <DocumentSection
      panel={standalone}
      title="提单"
      count={documents.bills.length}
      actions={
        editable && (
          <>
            <input
              ref={fileInput}
              type="file"
              accept="application/pdf,.pdf"
              multiple
              hidden
              aria-label="选择提单 PDF"
              onChange={(event) => {
                const files = Array.from(event.currentTarget.files ?? []);
                event.currentTarget.value = "";
                if (files.length) void uploadAll(files);
              }}
            />
            <Button variant="primary" size="sm" disabled={busy} onClick={() => fileInput.current?.click()}>
              {busy ? "处理中…" : "上传提单 PDF"}
            </Button>
          </>
        )
      }
    >
      {documents.bills.length ? (
        overview ? (
          <div className="settlement-group-bills">
            {documents.bills.map((bill) => (
              <article className="settlement-group-bill" key={bill.id}>
                <div className="settlement-group-bill__body">
                  <a href={bill.fileUrl} target="_blank" rel="noreferrer">
                    <strong>{bill.blNo || "提单编号待补"}</strong>
                  </a>
                  <p>
                    {bill.portOfLoading || "装运口岸待补"} → {bill.portOfDischarge || "目的口岸待补"} · 装船{" "}
                    {bill.onBoardDate || "日期待补"}
                  </p>
                  <p>覆盖：{bill.declarationNos.join("、")}</p>
                  {billColumns.find((column) => column.key === "state")?.render(bill)}
                </div>
                {editable && (
                  <div className="settlement-group-bill__actions">
                    {billColumns.find((column) => column.key === "actions")?.render(bill)}
                  </div>
                )}
              </article>
            ))}
          </div>
        ) : (
          <DataTable
            label="提单"
            columns={billColumns}
            rows={documents.bills}
            rowKey={(bill) => String(bill.id)}
            density="compact"
            minWidth={640}
          />
        )
      ) : (
        <p className="settlement-form__hint">
          还没有提单。上传后系统自动识别提单号、口岸与装船日期，识别不到的可人工填写。
        </p>
      )}
      {editingBill && (
        <BillEditForm
          key={editingBill.id}
          bill={editingBill}
          declarationNos={documents.declarationNos}
          busy={busy}
          onCancel={() => setEditing(null)}
          onSubmit={(fields) => void run(() => updateBill(target, editingBill.id, fields))}
        />
      )}
    </DocumentSection>
  );
  const contractContent = (
    <DocumentSection
      panel={standalone}
      title="销售合同（形式发票）"
      count={`${documents.contracts.length} / ${documents.planned.length}`}
      actions={
        editable && (
          <Button
            variant="primary"
            size="sm"
            disabled={busy || !documents.generate.allowed}
            title={documents.generate.reason}
            onClick={() => setGenerating(true)}
          >
            {documents.contracts.length ? "重新生成" : "按模板生成"}
          </Button>
        )
      }
    >
      {editable && !documents.generate.allowed && (
        <p className="settlement-form__hint">暂不能生成：{documents.generate.reason}</p>
      )}
      {standalone && !documents.planned.length && !documents.contracts.length ? (
        <EmptyState
          title="暂无销售合同依据"
          description={documents.generate.reason || "核对当前报关单的销售订单后再办理。"}
        />
      ) : (
        <DataTable
          label="销售合同（形式发票）"
          columns={contractColumns}
          rows={contractRows(documents)}
          rowKey={(row) => row.key}
          density="compact"
          minWidth={640}
        />
      )}
      {generating && (
        <ContractGenerateForm
          documents={documents}
          busy={busy}
          onCancel={() => setGenerating(false)}
          onSubmit={(body) => void run(() => generateContracts(target, body))}
        />
      )}
    </DocumentSection>
  );

  const footer = (
    <div className="settlement-form__actions settlement-batch__actions">
      {documents.package.allowed ? (
        <a className="ui-button ui-button--secondary" href={documents.packageUrl} download>
          下载资料包（zip）
        </a>
      ) : (
        <Button disabled title={documents.package.reason}>
          下载资料包（zip）
        </Button>
      )}
      {actions}
    </div>
  );

  return (
    <section className={standalone ? "settlement-page" : "settlement-docs"} aria-label="结汇资料">
      {!standalone && (
        <Alert
          tone={documents.complete ? (documents.warnings.length ? "warning" : "success") : "warning"}
          title={hasNoticeDetails ? undefined : noticeTitle}
        >
          {hasNoticeDetails && (
            <details className="settlement-docs__notice">
              <summary>
                <strong>{noticeTitle}</strong>{" "}
                <span className="settlement-docs__notice-expand">展开明细</span>
                <span className="settlement-docs__notice-collapse">收起明细</span>
              </summary>
              <ul className="settlement-docs__list">
                {[...documents.issues, ...documents.warnings].map((item, index) => (
                  <li key={`${index}-${item}`}>{item}</li>
                ))}
              </ul>
            </details>
          )}
          {!editable && <span> {documents.edit.reason}。</span>}
        </Alert>
      )}
      {standalone && !editable && (
        <Alert tone="info" title="当前资料状态">
          {documents.edit.reason}
        </Alert>
      )}

      {overview ? (
        <div className="settlement-docs__split">
          {overview(documents)}
          <Card>
            <CardContent>{billContent}</CardContent>
          </Card>
        </div>
      ) : (
        billContent
      )}

      {overview ? (
        <Card>
          <CardContent>{contractContent}</CardContent>
        </Card>
      ) : (
        contractContent
      )}
      <DocumentSection panel={standalone} title="报关单原件" count={documents.declarationFiles.length}>
        <p className="settlement-form__hint">
          取“开票跟进”从 NS 下载并归档的报关单原件；未归档时请到对应开票任务的详情中下载。
        </p>
        {standalone && !documents.declarationFiles.length ? (
          <EmptyState title="暂无报关单原件" description="请在开票跟进中核对报关单归档状态。" />
        ) : (
          <DataTable
            label="报关单文件"
            columns={declarationColumns}
            rows={documents.declarationFiles}
            rowKey={(row) => row.declarationNo}
            density="compact"
            minWidth={560}
          />
        )}
      </DocumentSection>

      {error && (
        <Alert tone="danger" title="操作未完成">
          {error}
        </Alert>
      )}
      {standalone ? (
        <Card>
          <CardHeader title="办理操作" />
          <CardContent>{footer}</CardContent>
        </Card>
      ) : (
        footer
      )}
    </section>
  );
}
