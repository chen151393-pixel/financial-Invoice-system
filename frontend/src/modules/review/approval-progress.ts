export interface ApprovalStatus {
  status: "approved" | "pending" | "changed" | "blocked";
  label: string;
  reason: string;
}

export interface ApprovalProgress {
  finance: ApprovalStatus;
  customs: ApprovalStatus;
  status:
    | "waiting_finance"
    | "waiting_customs"
    | "waiting_both"
    | "missing_receipt"
    | "blocked"
    | "created"
    | "reused"
    | "no_task"
    | "released";
  label: string;
  reason: string;
  nextStep: "finance" | "customs" | "both" | "import" | "tasks" | "details";
  linked?: boolean;
  taskIds: string[];
}

export interface ReviewLinks {
  finance?: (declarationNo: string) => string;
  customs?: (declarationNo: string, importing?: boolean) => string;
  task?: (taskId: string) => string;
}
