import { useState } from "react";
import { login, logout } from "../modules/identity/api";
import { LoginForm } from "../modules/identity/components/LoginForm";
import { connect, getStatus, type ConnectionStatus } from "../modules/sync/api";
import { ConnectionPanel } from "../modules/sync/components/ConnectionPanel";
import { queryRecords } from "../modules/business/api";
import { RecordQuery } from "../modules/business/components/RecordQuery";
import {
  createPreview,
  execute,
  getPreview,
  listJobs,
  type Job,
  type Operation,
  type Preview,
} from "../modules/writeback/api";
import { PreviewEditor } from "../modules/writeback/components/PreviewEditor";
import { PreviewPanel } from "../modules/writeback/components/PreviewPanel";
import { JobList } from "../modules/writeback/components/JobList";
import { useRequest } from "../shared/hooks/useRequest";

/** 页面只组合模块和协调UI状态，校验与可执行条件由后端返回。 */
export function WorkspacePage() {
  const { busy, message, setMessage, run } = useRequest();
  const [status, setStatus] = useState<ConnectionStatus | null>(null);
  const [type, setType] = useState("");
  const [id, setId] = useState("");
  const [record, setRecord] = useState<unknown>(null);
  const [operation, setOperation] = useState<Operation>("update");
  const [payload, setPayload] = useState("{}");
  const [preview, setPreview] = useState<Preview | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [jobs, setJobs] = useState<Job[]>([]);

  function resetPreview() {
    setPreview(null);
    setConfirmed(false);
  }
  async function refresh() {
    const [nextStatus, nextJobs] = await Promise.all([getStatus(), listJobs()]);
    setStatus(nextStatus);
    setJobs(nextJobs);
    setType((current) => current || nextStatus.recordTypes[0] || "");
  }
  async function loadPreview(previewId: string) {
    setConfirmed(false);
    setPreview(await getPreview(previewId));
  }

  return (
    <main className="live-app">
      <header className="live-header">
        <div>
          <p>NETSUITE · M2M</p>
          <h1>NS 数据校对与写回</h1>
          <span>拉取真实记录，核对修改内容，确认后由后端写入 NS。</span>
        </div>
        <a href="/demo">查看界面演示 ↗</a>
      </header>
      <div role="status" aria-live="polite" className="live-message">
        {busy ? "正在处理，请勿重复提交…" : message}
      </div>
      {!status ? (
        <LoginForm
          busy={busy}
          onLogin={(username, password) =>
            run(async () => {
              await login(username, password);
              await refresh();
            })
          }
        />
      ) : (
        <>
          <ConnectionPanel
            status={status}
            busy={busy}
            onConnect={() =>
              void run(async () => {
                const result = await connect();
                await refresh();
                setMessage(result.message);
              })
            }
            onLogout={() =>
              void run(async () => {
                await logout();
                setStatus(null);
                setRecord(null);
                setJobs([]);
                setPayload("{}");
                setId("");
                setType("");
                resetPreview();
              })
            }
          />
          <RecordQuery
            recordTypes={status.recordTypes}
            type={type}
            id={id}
            record={record}
            busy={busy}
            onType={(value) => {
              setType(value);
              setRecord(null);
              resetPreview();
            }}
            onId={(value) => {
              setId(value);
              setRecord(null);
              resetPreview();
            }}
            onQuery={(mode) =>
              void run(async () => {
                resetPreview();
                setRecord(null);
                setRecord((await queryRecords(type, id, mode)).data);
              })
            }
          />
          <PreviewEditor
            operation={operation}
            payload={payload}
            fields={status.writeFields[type] || []}
            busy={busy}
            onOperation={(value) => {
              setOperation(value);
              resetPreview();
            }}
            onPayload={(value) => {
              setPayload(value);
              resetPreview();
            }}
            onPreview={() =>
              void run(async () => {
                resetPreview();
                setPreview(await createPreview({ type, id, operation, payloadText: payload }));
                setJobs(await listJobs());
              })
            }
          />
          {preview && (
            <PreviewPanel
              preview={preview}
              confirmed={confirmed}
              busy={busy}
              onConfirm={setConfirmed}
              onExecute={() =>
                void run(async () => {
                  const previewId = preview.id;
                  setConfirmed(false);
                  await execute(previewId, confirmed);
                  await loadPreview(previewId);
                  setJobs(await listJobs());
                })
              }
              onRefresh={() => void run(() => loadPreview(preview.id))}
            />
          )}
          <JobList
            jobs={jobs}
            busy={busy}
            onRefresh={() => void run(refresh)}
            onSelect={(previewId) => void run(() => loadPreview(previewId))}
          />
        </>
      )}
    </main>
  );
}
