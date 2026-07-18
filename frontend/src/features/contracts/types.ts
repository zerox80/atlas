import type { ContractStateKey } from "../../utils/contractPresentation";

export type ContractViewFilter = "all" | ContractStateKey;

export interface ContractFilterCounts {
  all: number;
  attention: number;
  active: number;
  expired: number;
}

export const contractViewFilters: readonly {
  key: ContractViewFilter;
  label: string;
}[] = [
  { key: "all", label: "Alle" },
  { key: "attention", label: "Handlungsbedarf" },
  { key: "active", label: "Aktiv" },
  { key: "expired", label: "Archiv" },
];
