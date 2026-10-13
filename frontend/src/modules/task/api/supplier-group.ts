import { http } from "../../../shared/api/http";
import type {
  GroupBinding,
  GroupList,
  GroupPage,
  GroupQuery,
  GroupSave,
  SupplierOption,
  WecomGroupPage,
  WecomGroupQuery,
} from "../types/supplier-group";

const root = "/tasks/supplier-groups";

export const querySupplierGroups = (query: GroupQuery) => http<GroupList>(`${root}/query`, "POST", query);

export const querySuppliers = (keyword: string, page: number) =>
  http<GroupPage<SupplierOption>>(`${root}/suppliers/query`, "POST", { keyword, page });

export const saveSupplierGroup = (value: GroupSave) => http<GroupBinding>(`${root}/save`, "POST", value);

export const queryWecomGroups = (query: WecomGroupQuery) =>
  http<WecomGroupPage>(`${root}/wecom/query`, "POST", query);
