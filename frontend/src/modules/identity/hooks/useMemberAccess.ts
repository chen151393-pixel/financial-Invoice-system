import { useCallback, useEffect, useRef, useState } from "react";
import { getUserAccess, previewUserAccess, saveUserAccess } from "../api";
import type { UserAccessDetail, UserAccessPreview } from "../types";

type Draft = { roles: string[]; customRoles: boolean; enabled: boolean };
const message = (failure: unknown) => (failure instanceof Error ? failure.message : "成员权限操作失败");

/** 草稿只保留输入；继承角色、页面并集、启用条件和编辑版本全部来自后端。 */
export function useMemberAccess(id: number, onSaved: () => Promise<void>) {
  const [detail, setDetail] = useState<UserAccessDetail | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [preview, setPreview] = useState<UserAccessPreview | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [previewing, setPreviewing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const request = useRef(0);
  const submitting = useRef(false);
  const reload = useCallback(async () => {
    const current = ++request.current;
    setLoading(true);
    setError("");
    setSaved(false);
    setPreview(null);
    setPreviewing(false);
    try {
      const value = await getUserAccess(id);
      if (current === request.current) {
        setDetail(value);
        setPreview(value.preview);
        setDraft({ roles: value.personalRoles, customRoles: value.customRoles, enabled: value.enabled });
      }
    } catch (failure) {
      if (current === request.current) setError(message(failure));
    } finally {
      if (current === request.current) setLoading(false);
    }
  }, [id]);
  useEffect(() => {
    const current = ++request.current;
    getUserAccess(id)
      .then((value) => {
        if (current !== request.current) return;
        setDetail(value);
        setPreview(value.preview);
        setDraft({ roles: value.personalRoles, customRoles: value.customRoles, enabled: value.enabled });
      })
      .catch((failure: unknown) => {
        if (current === request.current) setError(message(failure));
      })
      .finally(() => {
        if (current === request.current) setLoading(false);
      });
    return () => {
      request.current += 1;
    };
  }, [id]);

  function change(next: Draft) {
    if (submitting.current) return;
    const current = ++request.current;
    setDraft(next);
    setPreview(null);
    setPreviewing(true);
    setError("");
    setSaved(false);
    void previewUserAccess(id, next.roles, next.customRoles)
      .then((result) => {
        if (current !== request.current) return;
        if (result.version !== detail?.preview.version)
          throw new Error("成员或角色权限已变化，请重新读取成员后再保存");
        setPreview(result);
      })
      .catch((failure: unknown) => {
        if (current === request.current) setError(message(failure));
      })
      .finally(() => {
        if (current === request.current) setPreviewing(false);
      });
  }
  async function save() {
    if (submitting.current || !draft || !preview || !detail || previewing || loading) return;
    submitting.current = true;
    setBusy(true);
    setError("");
    setSaved(false);
    try {
      await saveUserAccess(id, draft.roles, draft.customRoles, draft.enabled, detail.preview.version);
      // 已保存与后续列表刷新失败分开反馈，不诱导重复提交授权。
      await reload();
      setSaved(true);
      await onSaved();
    } catch (failure) {
      setError(message(failure));
    } finally {
      submitting.current = false;
      setBusy(false);
    }
  }
  return { detail, draft, preview, error, loading, previewing, busy, saved, reload, change, save };
}
