import { useCallback, useEffect, useRef, useState } from "react";
import * as api from "../api/delivery";
import type { Candidate, Candidates, Delivery, DeliveryController, DeliveryPreview } from "../types/delivery";

export function useDelivery(
  id: string,
  onChanged: () => Promise<void>,
  visible: boolean,
): DeliveryController {
  const [items, setItems] = useState<Delivery[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [preview, setPreview] = useState<DeliveryPreview | null>(null);
  const [candidates, setCandidates] = useState<Candidates | null>(null);
  const current = useRef(0);
  const executing = useRef(false);
  const requestId = useRef("");
  const reload = useCallback(async () => {
    const epoch = current.current;
    const data = await api.getDeliveries(id);
    if (epoch === current.current) setItems(data.items);
  }, [id]);
  useEffect(() => {
    const epoch = ++current.current;
    void api
      .getDeliveries(id)
      .then((data) => {
        if (current.current === epoch) setItems(data.items);
      })
      .catch((err: unknown) => {
        if (current.current === epoch) setError(err instanceof Error ? err.message : "发送记录读取失败");
      })
      .finally(() => {
        if (current.current === epoch) setLoading(false);
      });
    return () => {
      current.current = epoch + 1;
    };
  }, [id]);

  const run = useCallback(async (action: () => Promise<void>) => {
    if (executing.current) return;
    const epoch = current.current;
    executing.current = true;
    setBusy(true);
    setError("");
    try {
      await action();
    } catch (err) {
      if (epoch === current.current)
        setError(err instanceof Error ? err.message : "操作失败，请读取原执行记录核实");
    } finally {
      executing.current = false;
      if (epoch === current.current) setBusy(false);
    }
  }, []);
  const refresh = useCallback(
    async (deliveryId: string) => {
      const epoch = current.current;
      await run(async () => {
        await api.refreshDelivery(id, deliveryId);
        if (epoch !== current.current) return;
        await reload();
        await onChanged();
      });
    },
    [id, onChanged, reload, run],
  );
  useEffect(() => {
    const latest = items[0];
    if (!visible || !latest?.autoPoll) return;
    const timer = window.setInterval(() => {
      if (document.visibilityState === "visible") void refresh(latest.id);
    }, 30000);
    return () => window.clearInterval(timer);
  }, [items, refresh, visible]);
  async function prepare(revision: number, groupRevision: number) {
    const epoch = current.current;
    await run(async () => {
      const data = await api.previewDelivery(id, revision, groupRevision);
      if (epoch === current.current) {
        requestId.current = crypto.randomUUID();
        setPreview(data);
      }
    });
  }
  async function submit() {
    if (!preview) return;
    const epoch = current.current;
    await run(async () => {
      try {
        await api.submitDelivery(id, preview, requestId.current);
      } finally {
        if (epoch === current.current) {
          setPreview(null);
          // 网络断开也先读取持久执行记录；不自动更换 requestId 重新提交。
          await reload();
          await onChanged();
        }
      }
    });
  }
  async function findCandidates(deliveryId: string) {
    const epoch = current.current;
    await run(async () => {
      const data = await api.getCandidates(id, deliveryId);
      if (epoch === current.current) setCandidates(data);
    });
  }
  async function reconcile(deliveryId: string, candidate: Candidate, reason: string) {
    const epoch = current.current;
    await run(async () => {
      await api.reconcileDelivery(id, deliveryId, candidate, reason);
      if (epoch !== current.current) return;
      setCandidates(null);
      await reload();
      await onChanged();
    });
  }
  return {
    loading,
    busy,
    error,
    items,
    preview,
    candidates,
    prepare,
    submit,
    refresh,
    findCandidates,
    reconcile,
    reload: () => run(reload),
    closePreview: () => setPreview(null),
  };
}
