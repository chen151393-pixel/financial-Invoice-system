import { http } from "../../shared/api/http";
import type { AccessOverview, FeishuOutcome, LoginOptions, SessionInfo, SyncRun } from "./types";

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
export const syncDirectory = () => http<SyncRun | null>("/identity/sync", "POST", {});
export const saveScopes = (departmentIds: number[]) =>
  http<{ saved: boolean }>("/identity/scopes", "PUT", { departmentIds });
export const saveDepartmentRoles = (departmentId: number, roles: string[]) =>
  http<{ saved: boolean }>(`/identity/departments/${departmentId}/roles`, "PUT", { roles });
export const saveUserRoles = (userId: number, roles: string[], customRoles: boolean) =>
  http<{ saved: boolean }>(`/identity/users/${userId}/roles`, "PUT", { roles, customRoles });
