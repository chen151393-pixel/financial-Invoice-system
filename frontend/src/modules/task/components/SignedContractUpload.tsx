import { useState } from "react";
import { Button, Dialog, ErrorState, FileDropzone } from "../../../shared/components/ui";
import { useSignedUploads } from "../hooks/useSignedUploads";
import { SignedUploadResults } from "./SignedUploadResults";
import "./signed-contract-upload.css";

/** 每次打开均为新的上传会话；关闭只清空展示，完整接收的文件继续在后台归档。 */
export function SignedContractUpload({ onClose }: { onClose: (changed: boolean) => void }) {
  const [files, setFiles] = useState<File[]>([]);
  const state = useSignedUploads();
  return (
    <Dialog
      className="itd-upload-dialog"
      title="批量上传回签合同"
      busy={state.busy}
      onClose={() => onClose(state.changed)}
    >
      <div className="itd-upload">
        <p className="itd-upload__intro">上传后自动识别子采购单并保存到共享盘，仅展示本次处理结果。</p>
        <FileDropzone
          label="点击选择或拖入回签合同"
          hint="支持 PDF、JPG、PNG · 单个文件最高 100 MB · 可多选"
          accept=".pdf,.jpg,.jpeg,.png"
          multiple
          disabled={state.busy}
          onFiles={(selected) => setFiles((current) => [...current, ...selected])}
        />
        {files.length > 0 && (
          <section className="itd-upload__selection" aria-label="已选合同文件">
            <div className="itd-upload__job-heading">
              <strong>已选 {files.length} 个文件</strong>
              <Button size="sm" variant="ghost" disabled={state.busy} onClick={() => setFiles([])}>
                清空选择
              </Button>
            </div>
            <ul>
              {files.map((file, index) => (
                <li key={index}>
                  <span>{file.name}</span>
                  <Button
                    size="sm"
                    variant="ghost"
                    disabled={state.busy}
                    aria-label={`移除文件 ${file.name}`}
                    onClick={() => setFiles((current) => current.filter((_, i) => i !== index))}
                  >
                    移除
                  </Button>
                </li>
              ))}
            </ul>
          </section>
        )}
        <div className="itd-upload__actions">
          <Button
            variant="primary"
            disabled={state.busy || !files.length}
            onClick={() =>
              void state.submit(files).then((accepted) => {
                if (accepted) setFiles([]);
              })
            }
          >
            {state.busy ? "正在传输文件…" : files.length ? `开始上传 ${files.length} 个文件` : "开始上传"}
          </Button>
          <span className="itd-upload__muted">
            {state.busy ? "传输期间请保持窗口打开" : "文件名需包含子采购单号"}
          </span>
        </div>
        <details className="itd-upload__rules">
          <summary>上传说明</summary>
          <p>
            文件逐个上传，完整接收后自动进入后台队列，单个失败不影响其他文件。已有不同内容的回签合同不会覆盖。
          </p>
          <p>
            传输期间请保持页面打开，传完后可关闭。下次打开窗口将清空本次展示，已接收的文件继续在后台处理。
          </p>
        </details>
        {state.error && (
          <ErrorState
            title="上传任务操作失败"
            message={state.error}
            action={
              state.jobs.length > 0 ? (
                <Button disabled={state.busy || state.loading} onClick={() => void state.refresh()}>
                  重新查询本次结果
                </Button>
              ) : undefined
            }
          />
        )}
        {state.jobs.length > 0 && (
          <section className="itd-upload__results" aria-label="本次处理结果">
            <div className="itd-upload__job-heading">
              <h4>本次处理结果</h4>
              <Button size="sm" disabled={state.busy || state.loading} onClick={() => void state.refresh()}>
                {state.loading ? "正在刷新…" : "刷新结果"}
              </Button>
            </div>
            {state.jobs.map((job, index) => (
              <SignedUploadResults
                key={job.id}
                job={job}
                index={index}
                busy={state.busy}
                transfers={state.transfers}
                canResume={state.canResume}
                onRetry={(...args) => void state.retry(...args)}
              />
            ))}
          </section>
        )}
      </div>
    </Dialog>
  );
}
