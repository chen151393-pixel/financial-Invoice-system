// 与后端供应商群配置 VO 一致。
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
export interface WecomGroup extends GroupFields {
  memberCount: number;
  createdAt: string | null;
}
export interface WecomGroupPage extends GroupPage<WecomGroup> {
  unavailableCount: number;
}
export interface WecomGroupQuery {
  keyword: string;
  page: number;
  refresh: boolean;
}
