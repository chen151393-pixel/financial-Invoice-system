import type { SupplierGroupMatchQuery, WecomGroupPage } from "../types/supplier-group";

/** 串行轮询本地目录；刷新仅提交一次，关闭编辑区或切换查询时取消请求及计时器。 */
export function pollWecomDirectory(
  load: (query: SupplierGroupMatchQuery, signal?: AbortSignal) => Promise<WecomGroupPage>,
  query: SupplierGroupMatchQuery,
  onData: (data: WecomGroupPage) => void,
  onError: (error: unknown) => void,
) {
  const controller = new AbortController();
  let timer: ReturnType<typeof setTimeout> | undefined;
  async function read(refresh: boolean) {
    try {
      const data = await load({ ...query, refresh }, controller.signal);
      if (controller.signal.aborted) return;
      onData(data);
      if (data.directoryRefreshing) timer = setTimeout(() => void read(false), 1500);
    } catch (error) {
      if (!controller.signal.aborted) onError(error);
    }
  }
  void read(query.refresh);
  return () => {
    controller.abort();
    clearTimeout(timer);
  };
}
