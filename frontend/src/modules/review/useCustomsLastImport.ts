import { useEffect, useState } from "react";
import { queryCustomsLastImport } from "./customs-api";
import type { CustomsImportSource } from "./customs-types";

export type CustomsLastImportState =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; source: CustomsImportSource | null };

export function useCustomsLastImport(completedImports = "") {
  const [refresh, setRefresh] = useState(0);
  const [state, setState] = useState<CustomsLastImportState>({ kind: "loading" });
  useEffect(() => {
    const controller = new AbortController();
    async function load() {
      setState({ kind: "loading" });
      try {
        const result = await queryCustomsLastImport(controller.signal);
        if (!controller.signal.aborted) setState({ kind: "ready", source: result.items[0] ?? null });
      } catch (error) {
        if (controller.signal.aborted) return;
        setState({ kind: "error", message: error instanceof Error ? error.message : "上次导入结果读取失败" });
      }
    }
    void load();
    return () => controller.abort();
  }, [refresh, completedImports]);
  return { state, reload: () => setRefresh((value) => value + 1) };
}
