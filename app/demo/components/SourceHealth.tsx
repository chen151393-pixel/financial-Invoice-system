import type { View } from "../types";
export function SourceHealth({ navigate }: { navigate: (view: View) => void }) {
  return (
    <div className="source-health" role="status">
      <button onClick={() => navigate("sync")}>
        <i className="system-logo ns">N</i>
        <span>
          <strong>NetSuite Sandbox</strong>
          <small>业务单据已同步 · 10:26</small>
        </span>
        <em className="healthy">正常 · 延迟 2 分钟</em>
      </button>
      <button onClick={() => navigate("sync")}>
        <i className="system-logo lemon">柠</i>
        <span>
          <strong>柠檬云发票</strong>
          <small>发票批次 LY-0825-1028 · 10:28</small>
        </span>
        <em className="healthy">正常 · 新增 18 张</em>
      </button>
      <button onClick={() => navigate("reconcile")}>
        <i className="system-logo engine">⇄</i>
        <span>
          <strong>对账引擎</strong>
          <small>最新批次 RC-20260825-1030</small>
        </span>
        <em className="attention">3 项待处理</em>
      </button>
    </div>
  );
}
