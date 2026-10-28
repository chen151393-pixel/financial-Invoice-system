import { http } from "../../../shared/api/http";
import type {
  GroupBinding,
  GroupSave,
  InvoicingSpeed,
  SupplierProfileList,
  SupplierProfileQuery,
  SupplierGroupMatchQuery,
  SupplierNotify,
  WecomGroupPage,
} from "../types/supplier-group";

const root = "/tasks/supplier-groups";

export const saveSupplierGroup = (value: GroupSave) => http<GroupBinding>(`${root}/save`, "POST", value);

export const matchWecomGroups = (query: SupplierGroupMatchQuery) =>
  http<WecomGroupPage>(`${root}/wecom/match`, "POST", query);

export const querySupplierProfiles = (query: SupplierProfileQuery) =>
  http<SupplierProfileList>("/task/supplier-groups/profiles/query", "POST", query);

// 带当前版本保存；他人已修改时后端返回冲突，页面刷新后重试。
export const saveSupplierNotify = (supplierId: string, enabled: boolean, revision: number) =>
  http<SupplierNotify>(`${root}/profiles/notify`, "POST", { supplierId, enabled, revision });

export const getInvoicingSpeed = () => http<InvoicingSpeed>(`${root}/profiles/invoicing-speed`);
