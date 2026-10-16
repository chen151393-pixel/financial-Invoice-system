import { http } from "../../../shared/api/http";
import type {
  GroupBinding,
  GroupSave,
  SupplierProfileList,
  SupplierProfileQuery,
  SupplierGroupMatchQuery,
  WecomGroupPage,
} from "../types/supplier-group";

const root = "/tasks/supplier-groups";

export const saveSupplierGroup = (value: GroupSave) => http<GroupBinding>(`${root}/save`, "POST", value);

export const matchWecomGroups = (query: SupplierGroupMatchQuery) =>
  http<WecomGroupPage>(`${root}/wecom/match`, "POST", query);

export const querySupplierProfiles = (query: SupplierProfileQuery) =>
  http<SupplierProfileList>(`${root}/profiles/query`, "POST", query);
