import { Badge, DataTable, type Tone } from "../../../shared/components/ui";
import type { CustomsImportResult, ImportedDeclaration } from "../customs-types";

const consistent = (status: ImportedDeclaration["status"]) =>
  status === "matched" || status === "split_matched";
const CONSIGNEE_TONE: Record<ImportedDeclaration["consignee"]["state"], Tone> = {
  saved: "success",
  empty: "neutral",
  pending: "info",
};

export function ImportOutcome({ result }: { result: CustomsImportResult }) {
  return (
    <section className="cm-import__outcome" aria-label={`${result.fileName} 导入结果`}>
      <h4>
        {result.fileName}
        <span className="cm-muted">
          {result.rows} 行 · {result.declarations.length} 张报关单 · 新增 {result.created} · 更新{" "}
          {result.replaced} · 内容未变 {result.unchanged}
        </span>
      </h4>
      <p className="cm-muted">
        已识别列：{result.columns.join("、")}
        {result.ignoredColumns.length > 0 && `；未使用：${result.ignoredColumns.join("、")}`}
      </p>
      <DataTable
        label={`${result.fileName} 逐张结果`}
        density="compact"
        minWidth={560}
        maxHeight={260}
        rows={result.declarations}
        rowKey={(row) => row.declarationNo}
        columns={[
          { key: "no", header: "出口报关单号", render: (row) => row.declarationNo },
          { key: "items", header: "项数", align: "right", width: "56px", render: (row) => row.itemCount },
          { key: "result", header: "导入", width: "84px", render: (row) => row.resultLabel },
          {
            key: "status",
            header: "明细比对",
            render: (row) => (
              <Badge tone={consistent(row.status) ? "success" : "warning"}>{row.statusLabel}</Badge>
            ),
          },
          {
            key: "consignee",
            header: "境外收货人",
            render: (row) => <Badge tone={CONSIGNEE_TONE[row.consignee.state]}>{row.consignee.label}</Badge>,
          },
        ]}
      />
    </section>
  );
}
