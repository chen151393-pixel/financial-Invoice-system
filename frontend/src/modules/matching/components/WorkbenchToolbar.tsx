import { Button } from "../../../shared/components/Button";
import type { useWorkbench } from "../hooks/useWorkbench";

export function WorkbenchToolbar({ state }: { state: ReturnType<typeof useWorkbench> }) {
  return (
    <div className="wb-toolbar">
      <span>
        {state.data
          ? `更新于 ${new Date(state.data.generatedAt).toLocaleString("zh-CN", { timeZone: "Asia/Shanghai", hour12: false })}`
          : state.loading
            ? "正在更新数据…"
            : "数据暂不可用"}
      </span>
      <Button onClick={state.refresh} disabled={state.loading}>
        刷新
      </Button>
    </div>
  );
}
