import type { WecomGroupPage } from "../types/supplier-group";
import { formatTime } from "./format";

export function WecomDirectoryStatus({ data }: { data: WecomGroupPage }) {
  if (!data.directoryUpdatedAt) return null;
  return (
    <div className="it-help" role="status">
      <p>群目录更新时间：{formatTime(data.directoryUpdatedAt)}。保存时会实时核验所选群与群主。</p>
      {data.directoryRefreshing ? (
        <p>当前展示缓存结果，后台正在更新群目录。可稍后再次点击“查找外部群”查看更新结果。</p>
      ) : data.directoryStale ? (
        <p>当前展示缓存结果，可能不包含最近新增或改名的群；需要最新结果时点击“重新拉取”。</p>
      ) : null}
      {data.directoryRefreshError && (
        <p className="sg-feedback">群目录更新失败：{data.directoryRefreshError}。当前保留上次成功的目录。</p>
      )}
    </div>
  );
}
