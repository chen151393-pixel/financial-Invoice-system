import { Link } from "react-router";
import { paths } from "../../app/paths";
import { useEffect, useRef, useState } from "react";
import { Button } from "../../shared/components/Button";
import { openLocalSession } from "../identity/api";
import {
  confirmFile,
  getImportConfiguration,
  previewFile,
  readImportFile,
  type ImportConfiguration,
  type ImportFile,
  type ImportResult,
} from "./api";
import "./invoice-import.css";

export function InvoiceImport() {
  const [configuration, setConfiguration] = useState<ImportConfiguration | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [uploaded, setUploaded] = useState<ImportFile | null>(null);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const request = useRef(0);
  const table = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const dragDepth = useRef(0);

  function selectFiles(files: FileList | null) {
    if (busy || !configuration?.allowed) return;
    // 取消文件对话框或拖入文字时保留已选文件及预览。
    if (!files?.length) return;
    const selected = Array.from(files);
    // 先复制文件引用再清空原生输入，支持再次选择同一个文件。
    if (input.current) input.current.value = "";
    request.current += 1;
    setUploaded(null);
    setResult(null);
    setFile(null);
    setError("");
    if (selected.length > 1) {
      setError("每次只能导入一个文件，请重新选择或拖入。");
      return;
    }
    setFile(selected[0]);
  }
  useEffect(() => {
    let active = true;
    async function load() {
      try {
        await openLocalSession();
        const data = await getImportConfiguration();
        if (active) setConfiguration(data);
      } catch (error) {
        if (active) setError(error instanceof Error ? error.message : "读取导入配置失败");
      }
    }
    void load();
    return () => {
      active = false;
      request.current += 1;
    };
  }, [attempt]);

  async function run(confirm: boolean) {
    const id = ++request.current;
    setBusy(confirm ? "正在提交发票及全部明细…" : "正在读取文件并核对票头、明细和重复记录…");
    setError("");
    try {
      let data: ImportResult;
      if (confirm && uploaded && result?.previewToken) {
        data = await confirmFile(uploaded, result.previewToken);
      } else if (!confirm && file) {
        const value = await readImportFile(file);
        if (id !== request.current) return;
        setUploaded(value);
        data = await previewFile(value);
      } else {
        throw new Error("请先选择文件并预览");
      }
      if (id === request.current) setResult(data);
    } catch (error) {
      if (id === request.current) {
        setResult(null);
        setError(
          `${error instanceof Error ? error.message : "处理失败"}${confirm ? "。请重新预览核实已入库记录后再操作。" : ""}`,
        );
      }
    } finally {
      if (id === request.current) setBusy("");
    }
  }

  return (
    <section className="sync-page__panel invoice-import" aria-busy={Boolean(busy)}>
      <div className="sync-page__heading">
        <div>
          <h2>导入进项发票</h2>
          <p>上传柠檬云导出的 Excel，仅导入业务类型为“采购固定资产”的发票。</p>
        </div>
        <span className="sync-page__tag">Excel 导入 · API 同步待接入</span>
      </div>
      {!configuration && !error && <p role="status">正在检查发票数据库…</p>}
      {configuration && !configuration.allowed && (
        <p role="alert" className="sync-page__error">
          {configuration.reason}
        </p>
      )}
      <form
        className={`invoice-import__dropzone${dragging ? " invoice-import__dropzone--active" : ""}`}
        onDragEnter={(event) => {
          if (!event.dataTransfer.types.includes("Files")) return;
          event.preventDefault();
          if (busy || !configuration?.allowed) return;
          dragDepth.current += 1;
          setDragging(true);
        }}
        onDragOver={(event) => {
          if (!event.dataTransfer.types.includes("Files")) return;
          event.preventDefault();
          event.dataTransfer.dropEffect = busy || !configuration?.allowed ? "none" : "copy";
        }}
        onDragLeave={(event) => {
          event.preventDefault();
          dragDepth.current = Math.max(0, dragDepth.current - 1);
          if (dragDepth.current === 0) setDragging(false);
        }}
        onDrop={(event) => {
          event.preventDefault();
          dragDepth.current = 0;
          setDragging(false);
          if (busy || !configuration?.allowed) return;
          selectFiles(event.dataTransfer.files);
        }}
        onSubmit={(event) => {
          event.preventDefault();
          void run(false);
        }}
      >
        <fieldset disabled={Boolean(busy) || !configuration?.allowed}>
          <legend>{dragging ? "松开以选择文件" : "将 Excel 拖到此处，或选择文件"}</legend>
          <span>进项发票 Excel（.xls / .xlsx）</span>
          <input
            id="invoice-file"
            ref={input}
            type="file"
            hidden
            aria-label="进项发票 Excel（.xls / .xlsx）"
            accept=".xls,.xlsx"
            aria-describedby="invoice-file-help"
            onChange={(event) => selectFiles(event.target.files)}
          />
          <div className="invoice-import__file-picker">
            <Button type="button" onClick={() => input.current?.click()}>
              {file ? "重新选择文件" : "选择文件"}
            </Button>
            <p className="invoice-import__filename" role="status">
              {file ? `已选择：${file.name}` : "未选择文件，可将文件拖入此虚线区域"}
            </p>
          </div>
          <p id="invoice-file-help">
            文件不超过 4MB，支持票头与商品在同一张表的 34
            列合并格式（表名不限），也支持“发票信息”和“货物信息”双表格式。 每次最多 1000
            张数电进项票；合计行用于核对，不作为商品重复导入。预览不会写入数据库。
            仅导入原表业务类型为“采购固定资产”的发票，其他类型跳过。
          </p>
          <Button type="submit" variant="primary" disabled={!file || Boolean(busy)}>
            {result ? "重新预览并核实" : "解析并预览"}
          </Button>
        </fieldset>
      </form>
      {busy && <p role="status">{busy}</p>}
      {error && (
        <p role="alert" className="sync-page__error">
          {error}
        </p>
      )}
      {(!configuration || !configuration.allowed) && !busy && (
        <Button
          onClick={() => {
            setError("");
            setAttempt((value) => value + 1);
          }}
        >
          重新检查配置
        </Button>
      )}
      {!result && !busy && !error && (
        <div className="sync-page__empty">
          <strong>{file ? "文件已选择，点击“解析并预览”继续" : "等待选择文件"}</strong>
          <p>系统会核对每张票的金额、税额和明细，识别重复与冲突，不自动覆盖已保存的发票。</p>
        </div>
      )}
      {result && (
        <>
          <div className="invoice-import__summary" role="status">
            <strong>{result.message}</strong>
            <p>{result.filename}</p>
            <p>
              文件共 {result.sourceInvoiceCount} 张 · 导入类型：{result.businessType} · 其他类型已跳过{" "}
              {result.excludedCount} 张
            </p>
            <p>
              本次范围 {result.invoiceCount} 张发票 / {result.lineCount} 行明细 ·{" "}
              {result.saved ? "已新增" : "待新增"} {result.created} 张 · 重复 {result.unchanged} 张 · 冲突{" "}
              {result.conflicts} 张
            </p>
            <p>本次范围价税合计：{result.amount}（币种待核实）</p>
          </div>
          <ul className="invoice-import__warnings">
            {result.warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
          {!result.saved && (
            <div className="invoice-import__actions">
              <Button
                variant="primary"
                disabled={Boolean(busy) || !result.allowed}
                onClick={() => void run(true)}
              >
                确认导入数据库
              </Button>
              <span>{result.reason}；重复记录跳过，冲突时整批不写入。</span>
            </div>
          )}
          <div className="invoice-import__actions" aria-label="表格滚动">
            <Button onClick={() => table.current?.scrollBy({ left: -320 })}>向左查看列</Button>
            <Button onClick={() => table.current?.scrollBy({ left: 320 })}>向右查看列</Button>
          </div>
          <div
            className="sync-page__table invoice-import__table"
            ref={table}
            role="region"
            aria-label="发票导入核对表，可横向滚动"
          >
            <table>
              <caption>{result.saved ? "本次导入结果" : "导入前核对"}</caption>
              <thead>
                <tr>
                  <th scope="col">发票号码</th>
                  <th scope="col">开票日期</th>
                  <th scope="col">供应商</th>
                  <th scope="col">业务类型</th>
                  <th scope="col">来源状态</th>
                  <th scope="col">明细行数</th>
                  <th scope="col">价税合计</th>
                  <th scope="col">{result.saved ? "处理结果" : "预计处理"}</th>
                </tr>
              </thead>
              <tbody>
                {result.rows.map((row) => (
                  <tr key={row.number}>
                    <td>{row.number}</td>
                    <td>{row.date}</td>
                    <td>{row.seller}</td>
                    <td>{row.businessType}</td>
                    <td>{row.status}</td>
                    <td>{row.lineCount}</td>
                    <td className="invoice-import__amount">{row.amount}</td>
                    <td>
                      {row.action === "new"
                        ? result.saved
                          ? "已入库 · 待核实"
                          : "新增 · 待核实"
                        : row.action === "unchanged"
                          ? "重复 · 跳过"
                          : "冲突 · 需核实"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {result.saved && (
            <p>
              发票已保存在数据库。<Link to={paths.invoices}>查看已入库发票</Link>
              ；重新选择同一文件预览，可以核实重复记录。
            </p>
          )}
        </>
      )}
    </section>
  );
}
