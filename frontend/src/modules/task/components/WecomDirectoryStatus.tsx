import type { WecomGroupPage } from "../types/supplier-group";
import { formatTime } from "./format";
import { Alert, Progress } from "../../../shared/components/ui";

export function WecomDirectoryStatus({ data }: { data: WecomGroupPage }) {
  if (!data.directoryState && !data.directoryUpdatedAt) return null;
  return (
    <div className="it-help" role="status">
      {data.directoryUpdatedAt && (
        <p>群目录更新时间：{formatTime(data.directoryUpdatedAt)}。保存时会实时核验所选群与群主。</p>
      )}
      {data.directoryRefreshing ? (
        <>
          <p>
            {data.directoryHasSnapshot === false
              ? "首次群目录同步中，完成后自动显示匹配结果。"
              : "后台正在更新群目录，可继续查询和选择已有结果。"}
            关闭页面后仍会继续同步。
          </p>
          {data.directoryState === "queued" && <p>已加入后台同步队列，等待开始…</p>}
          {data.directoryState === "listing" && (
            <p>正在获取群列表，已发现 {data.directoryDiscovered} 个群，总数确认中…</p>
          )}
          {data.directoryState === "details" && (
            <>
              <p>
                正在读取群详情：已处理 {data.directoryCompleted} / {data.directoryTotal} 个群。
              </p>
              {data.directoryPercent != null && (
                <Progress
                  width={data.directoryPercent}
                  text={`${data.directoryPercent}%`}
                  label="群目录同步进度"
                />
              )}
              {data.directoryCompleted === data.directoryTotal && <p>详情读取完成，正在保存完整目录…</p>}
            </>
          )}
        </>
      ) : data.directoryStale ? (
        data.directoryHasSnapshot !== false && (
          <p>当前展示本地目录，可能不包含最近新增或改名的群；需要最新结果时点击“同步群目录”。</p>
        )
      ) : null}
      {data.directoryRefreshError && (
        <Alert tone="warning">
          群目录更新失败：{data.directoryRefreshError}。
          {data.directoryHasSnapshot === false
            ? "暂无可用目录，请检查配置后点击“同步群目录”重试。"
            : "当前保留上次成功的目录，可继续搜索或点击“同步群目录”重试。"}
        </Alert>
      )}
    </div>
  );
}
