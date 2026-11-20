import type { HkReceiptDraft } from "../types/hk-receipt";
// 只保存当前浏览器页生命周期中的登记草稿，让“返回补选”保留输入和已选水单；不写本地持久存储。
let draft: HkReceiptDraft | null = null;
export const readHkReceiptDraft = (id: string) => (draft?.id === id ? draft : null);
export const saveHkReceiptDraft = (value: HkReceiptDraft) => {
  draft = value;
};
export const clearHkReceiptDraft = (id: string) => {
  if (draft?.id === id) draft = null;
};
