import { http } from "../../shared/api/http";
import type { AccessOverview, FeishuOutcome, LoginOptions, SessionInfo, SyncRun } from "./types";
import type {
  DirectoryMembers,
  DirectoryPlan,
  DirectoryPreview,
  DirectorySelection,
  UserList,
} from "./types";

export const getSession = () => http<SessionInfo>("/session");
export const getLoginOptions = () => http<LoginOptions>("/session/options");
export const login = (username: string, password: string) =>
  http<{ authenticated: boolean }>("/session", "POST", { username, password });
export const logout = () => http<{ authenticated: boolean }>("/session", "DELETE");

// 飞书登录：后端登记一次性 state 并返回授权地址，浏览器整页跳转到飞书
export const startFeishuLogin = (returnTo: string) =>
  http<{ url: string }>("/session/feishu/start", "POST", { returnTo });
export const getFeishuOutcome = () => http<FeishuOutcome>("/session/feishu/outcome");

// 兼容现有业务调用方：只检查会话，不再签发本机免密会话。
export const openLocalSession = getSession;

// 人员与权限（仅系统管理员）
export const getAccess = () => http<AccessOverview>("/identity/access");
export const saveDepartmentRoles = (departmentId: number, roles: string[]) =>
  http<{ saved: boolean }>(`/identity/departments/${departmentId}/roles`, "PUT", { roles });

export const previewDirectory = () => http<DirectoryPreview>("/identity/directory/previews", "POST", {});
export const queryDirectoryMembers = (
  id: string,
  selection: DirectorySelection,
  departmentId: string,
  query: string,
  page: number,
) =>
  http<DirectoryMembers>(`/identity/directory/previews/${id}/members`, "POST", {
    ...selection,
    departmentId,
    query,
    page,
  });
export const planDirectory = (id: string, selection: DirectorySelection) =>
  http<DirectoryPlan>(`/identity/directory/previews/${id}/plan`, "POST", selection);
export const confirmDirectory = (id: string, selection: DirectorySelection) =>
  http<{ run: SyncRun; userIds: number[] }>(`/identity/directory/previews/${id}/sync`, "POST", selection);
export const queryAccessUsers = (query: string, departmentId: string, page: number) =>
  http<UserList>(
    `/identity/users?${new URLSearchParams({ query, page: String(page), ...(departmentId ? { department_id: departmentId } : {}) })}`,
  );
export const saveUserAccess = (id: number, roles: string[], customRoles: boolean, enabled: boolean) =>
  http<{ saved: boolean }>(`/identity/users/${id}/access`, "PUT", { roles, customRoles, enabled });
