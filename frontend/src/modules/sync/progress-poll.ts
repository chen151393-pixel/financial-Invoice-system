import type { SyncProgress } from "./api";

// 单个只读请求串行轮询；进度不可用不会重发保存，也不把进度完成当作保存响应。
export function pollProgress({
  read,
  onProgress,
  onUnavailable,
  isCurrent,
  delay = 1000,
}: {
  read: () => Promise<SyncProgress>;
  onProgress: (progress: SyncProgress) => void;
  onUnavailable: () => void;
  isCurrent: () => boolean;
  delay?: number;
}) {
  let disposed = false;
  let timer: ReturnType<typeof setTimeout> | undefined;
  const active = () => !disposed && isCurrent();
  async function poll() {
    if (!active()) return;
    try {
      const progress = await read();
      if (active()) onProgress(progress);
    } catch {
      if (active()) onUnavailable();
    } finally {
      if (active()) timer = setTimeout(() => void poll(), delay);
    }
  }
  void poll();
  return () => {
    disposed = true;
    clearTimeout(timer);
  };
}
