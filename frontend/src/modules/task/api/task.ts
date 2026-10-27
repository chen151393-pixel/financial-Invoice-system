import type { ClosureRequest } from "../types/task";
import { http } from "../../../shared/api/http";
import type {
  DeclarationDocumentType,
  NotificationDraft,
  NotificationRecord,
  TaskDetail,
} from "../types/task";

const root = "/tasks";
const task = (id: string) => `${root}/${encodeURIComponent(id)}`;

export const getTask = (id: string) => http<TaskDetail>(task(id));

export const prepareTaskDocument = (id: string, orderId: string) =>
  http<TaskDetail>(`${task(id)}/documents/${encodeURIComponent(orderId)}/prepare`, "POST", {});

// 报关资料单项重试或重新下载；后端在 NS 重新定位报关单，内容不同时不覆盖已归档文件。
export const prepareDeclarationDocument = (id: string, type: DeclarationDocumentType) =>
  http<TaskDetail>(`${task(id)}/declaration-documents/${type}/prepare`, "POST", {});

export const saveTaskNotification = (id: string, draft: NotificationDraft) =>
  http<TaskDetail>(`${task(id)}/notification/draft`, "POST", draft);

export const recordTaskNotification = (id: string, record: NotificationRecord) =>
  http<TaskDetail>(`${task(id)}/notification/record`, "POST", record);

export const closeTaskLine = (id: string, lineId: string, body: ClosureRequest) =>
  http<TaskDetail>(
    `/tasks/${encodeURIComponent(id)}/lines/${encodeURIComponent(lineId)}/close`,
    "POST",
    body,
  );
