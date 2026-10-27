// 与后端供应商群配置 VO 一致。
export interface GroupFields {
  groupName: string;
  chatId: string;
  employee: string;
  userid: string;
}
export interface SupplierOption {
  binding?: GroupBinding | null;
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
  matchReason: string;
  memberCount: number;
  createdAt: string | null;
}
export interface WecomGroupPage extends GroupPage<WecomGroup> {
  unavailableCount: number;
  directoryUpdatedAt?: string | null;
  directoryStale?: boolean;
  directoryRefreshing?: boolean;
  directoryRefreshError?: string;
}
export interface WecomGroupQuery {
  keyword: string;
  page: number;
  refresh: boolean;
}

export interface SupplierGroupMatchQuery extends WecomGroupQuery {
  supplierId: string;
}

// 是否开启供应商通知：关闭后财务审核通过不生成该供应商的开票任务；revision 为 0 表示从未设置（默认开启）。
export interface SupplierNotify {
  enabled: boolean;
  revision: number;
  updatedBy: string;
  updatedAt: string | null;
}
export interface SupplierProfile extends SupplierOption {
  nsInternalId: string;
  notify: SupplierNotify;
}
// 上线只同步 NS 正式环境，档案查询不再按 NS 环境筛选（后端参数保留为可选）
export interface SupplierProfileQuery extends Omit<GroupQuery, "status" | "account"> {
  status: GroupQuery["status"] | "unbound";
}
export interface SupplierProfileList extends GroupPage<SupplierProfile> {
  manage: GroupList["manage"];
  // 档案概况，不受关键字与状态筛选影响
  counts: { all: number; bound: number; unbound: number; notifyOff: number };
}
