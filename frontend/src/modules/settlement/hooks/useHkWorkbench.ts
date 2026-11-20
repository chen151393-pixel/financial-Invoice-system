import { useEffect, useState } from "react";
import { queryHkWorkbench } from "../api/hk-workbench-api";
import type { HkWorkbench, HkWorkbenchQuery } from "../types/hk-workbench";
type State =
  | { kind: "loading" }
  | { kind: "ready"; result: HkWorkbench }
  | { kind: "error"; message: string };
export function useHkWorkbench(query: HkWorkbenchQuery) {
  const [revision, setRevision] = useState(0);
  const key = JSON.stringify([query, revision]);
  const [snapshot, setSnapshot] = useState<{ key: string; state: State }>({
    key: "",
    state: { kind: "loading" },
  });
  useEffect(() => {
    const controller = new AbortController();
    const [submitted] = JSON.parse(key) as [HkWorkbenchQuery, number];
    queryHkWorkbench(submitted, controller.signal)
      .then((result) => {
        if (!controller.signal.aborted) setSnapshot({ key, state: { kind: "ready", result } });
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted)
          setSnapshot({
            key,
            state: {
              kind: "error",
              message: error instanceof Error ? error.message : "香港中转工作区读取失败",
            },
          });
      });
    return () => controller.abort();
  }, [key]);
  const state: State = snapshot.key === key ? snapshot.state : { kind: "loading" };
  return { state, reload: () => setRevision((value) => value + 1) };
}
