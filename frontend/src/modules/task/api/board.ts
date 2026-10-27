import { http } from "../../../shared/api/http";
import type { TaskBoard, TaskBoardQuery } from "../types/board";

export const queryTaskBoard = (query: TaskBoardQuery) =>
  http<TaskBoard>("/tasks/board/query", "POST", {
    ...query,
    ...(query.createdFrom !== undefined ? { createdFrom: query.createdFrom || null } : {}),
    ...(query.createdTo !== undefined ? { createdTo: query.createdTo || null } : {}),
  });
