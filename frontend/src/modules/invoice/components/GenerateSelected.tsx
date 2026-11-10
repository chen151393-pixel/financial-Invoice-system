import { useState } from "react";
import { Button } from "../../../shared/components/ui";
import { generateProposals } from "../../matching/api";

/**
 * 查询栏右侧“批量生成建议”：对列表中勾选的发票重新生成比对建议（与比对页“重新生成建议”同一接口和规则）。
 * 哪些发票、哪些发票行能生成由后端判定；这里只提交勾选的发票 ID 并回传真实结果。
 */
export function GenerateSelected({
  ids,
  disabled,
  onDone,
  onError,
}: {
  ids: string[];
  disabled: boolean;
  onDone: (invoices: number, created: number) => void;
  onError: (message: string) => void;
}) {
  const [busy, setBusy] = useState(false);

  async function run() {
    setBusy(true);
    try {
      const result = await generateProposals(ids);
      onDone(ids.length, result.created);
    } catch (cause) {
      // 写操作不自动重试；结果不明时刷新列表核实，再次提交不会重复追加相同建议
      onError(cause instanceof Error ? cause.message : "批量生成建议失败，请刷新列表核实结果");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Button disabled={disabled || busy || ids.length === 0} onClick={() => void run()}>
      {busy ? "正在生成…" : `批量生成建议（已选 ${ids.length} 张）`}
    </Button>
  );
}
