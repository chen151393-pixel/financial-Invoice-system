import { useEffect, useRef, useState } from "react";
import {
  Alert,
  Badge,
  Button,
  DataTable,
  ErrorState,
  SectionTitle,
  Skeleton,
  type Column,
} from "../../../shared/components/ui";
import { money } from "../../../shared/format/money";
import { generateContracts, getDocuments, removeBill, updateBill, uploadBill } from "../api";
import type { BatchDocuments as Documents, Bill, Contract, PlannedContract } from "../types";
import { BillEditForm } from "./BillEditForm";
import { ContractGenerateForm } from "./ContractGenerateForm";

type State =
  | { kind: "loading" }
  | { kind: "ready"; documents: Documents }
  | { kind: "error"; message: string };
type ContractRow = { planned: PlannedContract | null; contract: Contract | null; contractNo: string };

function contractRows(documents: Documents): ContractRow[] {
  const generated = new Map(documents.contracts.map((contract) => [contract.contractNo, contract]));
  const rows: ContractRow[] = documents.planned.map((planned) => ({
    planned,
    contract: generated.get(planned.contractNo) ?? null,
    contractNo: planned.contractNo,
  }));
  const plannedNos = new Set(documents.planned.map((planned) => planned.contractNo));
  for (const contract of documents.contracts) {
    if (!plannedNos.has(contract.contractNo)) {
      rows.push({ planned: null, contract, contractNo: contract.contractNo });
    }
  }
  return rows;
}

/** 香港中转批次的结汇资料：提单、销售合同、资料包。齐全度、缺项与能否操作全部来自后端。 */
export function BatchDocuments({ batchId, onChanged }: { batchId: number; onChanged: () => void }) {
  const [state, setState] = useState<State>({ kind: "loading" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [editing, setEditing] = useState<number | null>(null);
  const [generating, setGenerating] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const fileInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const controller = new AbortController();
    getDocuments(batchId, controller.signal)
      .then((documents) => setState({ kind: "ready", documents }))
      .catch((reason: unknown) => {
        if (reason instanceof Error && reason.name === "AbortError") return;
        setState({ kind: "error", message: reason instanceof Error ? reason.message : "加载失败" });
      });
    return () => controller.abort();
  }, [batchId, refresh]);

  async function run(action: () => Promise<Documents>) {
    setBusy(true);
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
    }
  }

  async function uploadAll(files: File[]) {
    setBusy(true);
    setError("");
    const failed: string[] = [];
    for (const file of files) {
      try {
        setState({ kind: "ready", documents: await uploadBill(batchId, file) });
      } catch (reason) {
        failed.push(`${file.name}：${reason instanceof Error ? reason.message : "上传失败"}`);
      }
    }
    if (failed.length) setError(failed.join("；"));
    setBusy(false);
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
      render: (bill) =>
        bill.missing.length ? (
          <Badge tone="warning">待补：{bill.missing.join("、")}</Badge>
        ) : (
          <Badge tone="success">信息完整</Badge>
        ),
    },
    {
      key: "actions",
      header: "操作",
      render: (bill) =>
        editable ? (
          <div className="settlement-badges">
            <Button size="sm" disabled={busy} onClick={() => setEditing(bill.id)}>
              修改
            </Button>
            <Button
              size="sm"
              variant="ghost"
              disabled={busy}
              onClick={() => {
                if (window.confirm(`移除提单 ${bill.blNo || bill.fileName}？`)) {
                  void run(() => removeBill(batchId, bill.id));
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
  const contractColumns: Column<ContractRow>[] = [
    {
      key: "no",
      header: "合同编号",
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
      key: "amount",
      header: "合同金额",
      align: "right",
      render: (row) => {
        const source = row.planned ?? row.contract;
        return source ? `${source.currency} ${money(source.amount)}` : "";
      },
    },
    { key: "date", header: "签订日期", render: (row) => row.contract?.contractDate || "—" },
    {
      key: "ports",
      header: "装运口岸 → 目的口岸",
      render: (row) =>
        row.contract ? `${row.contract.portOfLoading} → ${row.contract.portOfDestination}` : "—",
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

  return (
    <section className="settlement-docs" aria-label="结汇资料">
      <Alert
        tone={documents.complete ? (documents.warnings.length ? "warning" : "success") : "warning"}
        title={
          documents.complete ? "提单与销售合同已齐全" : `资料未齐，还有 ${documents.issues.length} 项待处理`
        }
      >
        {(documents.issues.length > 0 || documents.warnings.length > 0) && (
          <ul className="settlement-docs__list">
            {[...documents.issues, ...documents.warnings].map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        )}
        <span>未纳入资料包、需另行准备：{documents.notIncluded.join("、")}。</span>
        {!editable && <span> {documents.edit.reason}。</span>}
      </Alert>

      <SectionTitle
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
      />
      {documents.bills.length ? (
        <DataTable
          label="提单"
          columns={billColumns}
          rows={documents.bills}
          rowKey={(bill) => String(bill.id)}
          density="compact"
          minWidth={640}
        />
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
          onSubmit={(fields) => void run(() => updateBill(batchId, editingBill.id, fields))}
        />
      )}

      <SectionTitle
        title="销售合同"
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
      />
      {editable && !documents.generate.allowed && (
        <p className="settlement-form__hint">暂不能生成：{documents.generate.reason}</p>
      )}
      <DataTable
        label="销售合同"
        columns={contractColumns}
        rows={contractRows(documents)}
        rowKey={(row) => row.contractNo}
        density="compact"
        minWidth={640}
      />
      {generating && (
        <ContractGenerateForm
          documents={documents}
          busy={busy}
          onCancel={() => setGenerating(false)}
          onSubmit={(body) => void run(() => generateContracts(batchId, body))}
        />
      )}

      {error && (
        <Alert tone="danger" title="操作未完成">
          {error}
        </Alert>
      )}
      <div className="settlement-form__actions">
        {documents.package.allowed ? (
          <a className="ui-button ui-button--secondary" href={documents.packageUrl} download>
            下载资料包（zip）
          </a>
        ) : (
          <Button disabled title={documents.package.reason}>
            下载资料包（zip）
          </Button>
        )}
      </div>
    </section>
  );
}
