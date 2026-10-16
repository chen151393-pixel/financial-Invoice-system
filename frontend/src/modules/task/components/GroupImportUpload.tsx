import { useRef, useState } from "react";
import { Button } from "../../../shared/components/Button";
import { previewGroups, readImportFile } from "../api/external-group";
export function GroupImportUpload({ onPreview }: { onPreview: (id: string) => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const file = useRef<HTMLInputElement>(null);
  return (
    <section className="sg-editor">
      <h2>导入外部群 Excel</h2>
      <p className="it-help">
        表头依次为：群名、群人数、群主、群主所在部门、创建时间、外部群id、群主id。仅支持 .xlsx，最多 1000
        行、4MB。群人数、创建时间可留空，格式不限，不影响导入；无法识别时显示“未提供”。
      </p>
      <form
        className="sg-row"
        onSubmit={(e) => {
          e.preventDefault();
          const f = new FormData(e.currentTarget);
          const selected = file.current?.files?.[0];
          if (!selected) {
            setError("请先选择外部群 Excel 文件");
            return;
          }
          setBusy(true);
          setError("");
          void readImportFile(selected)
            .then((data) => previewGroups(data, String(f.get("account") || "")))
            .then((result) => onPreview(result.importId))
            .catch((reason: unknown) =>
              setError(reason instanceof Error ? reason.message : "预览失败，请重新上传"),
            )
            .finally(() => setBusy(false));
        }}
      >
        <label>
          外部群文件
          <input ref={file} type="file" accept=".xlsx" disabled={busy} />
        </label>
        <label>
          匹配 NS 环境
          <input name="account" placeholder="留空匹配全部环境" disabled={busy} />
        </label>
        <Button type="submit" variant="primary" disabled={busy}>
          {busy ? "正在解析…" : "上传并预览匹配"}
        </Button>
      </form>
      {error && <p role="alert">{error}</p>}
      <p className="it-help">
        上传只生成预览。确认后保存有效群及所选绑定；未匹配的群进入目录，后续可手动关联。
      </p>
    </section>
  );
}
