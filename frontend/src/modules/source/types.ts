export interface PlSearchCriteria {
  type: "pl" | "customsRecord" | "declaration";
  pl: string;
  month: string;
  createdFrom: string;
  createdTo: string;
  showIncomplete: boolean;
}
