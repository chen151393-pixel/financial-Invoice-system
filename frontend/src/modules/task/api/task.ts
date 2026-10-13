import { http } from "../../../shared/api/http";
import type {
  NotificationDraft,
  NotificationRecord,
  TaskDetail,
  TaskList,
  TaskListQuery,
} from "../types/task";

const root = "/tasks";
const task = (id: string) => `${root}/${encodeURIComponent(id)}`;

export const listTasks = (query: TaskListQuery) => http<TaskList>(`${root}/query`, "POST", query);

export const getTask = (id: string) => http<TaskDetail>(task(id));

export const prepareTaskDocument = (id: string, orderId: string) =>
  http<TaskDetail>(`${task(id)}/documents/${encodeURIComponent(orderId)}/prepare`, "POST", {});

export const saveTaskNotification = (id: string, draft: NotificationDraft) =>
  http<TaskDetail>(`${task(id)}/notification/draft`, "POST", draft);

export const recordTaskNotification = (id: string, record: NotificationRecord) =>
  http<TaskDetail>(`${task(id)}/notification/record`, "POST", record);
