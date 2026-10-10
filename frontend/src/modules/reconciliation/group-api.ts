import { http } from "../../shared/api/http";

export interface GroupFields {
  groupName: string;
  chatId: string;
  employee: string;
  userid: string;
}
export interface SupplierOption {
  account: string;
  supplierId: string;
  supplierName: string;
}
export interface GroupBinding extends GroupFields, SupplierOption {
  revision: number;
  enabled: boolean;
  updatedAt: string;
}
export interface GroupSave {
  chatId: string;
  account: string;
  supplierId: string;
  revision: number;
  enabled: boolean;
}
export interface GroupQuery {
  keyword: string;
  account: string;
  status: "all" | "enabled" | "disabled";
  page: number;
  pageSize: number;
}
export interface GroupPage<T> {
  items: T[];
  total: number;
  page: number;
  pageSize: number;
  pages: number;
}
export interface GroupList extends GroupPage<GroupBinding> {
  manage: { allowed: boolean; reason: string };
}
const root = "/reconciliation/supplier-groups";
export const querySupplierGroups = (query: GroupQuery) => http<GroupList>(root + "/query", "POST", query);
export const querySuppliers = (keyword: string, page: number) =>
  http<GroupPage<SupplierOption>>(root + "/suppliers/query", "POST", { keyword, page });
export const saveSupplierGroup = (value: GroupSave) => http<GroupBinding>(root + "/save", "POST", value);

export interface WecomGroup extends GroupFields {
  memberCount: number;
  createdAt: string | null;
}
export interface WecomGroupPage extends GroupPage<WecomGroup> {
  unavailableCount: number;
}
export const queryWecomGroups = (query: { keyword: string; page: number; refresh: boolean }) =>
  http<WecomGroupPage>(root + "/wecom/query", "POST", query);
