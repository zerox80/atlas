import type { Contract } from "../../types";
import { getContractState } from "../../utils/contractPresentation";
import { matchesDocumentSearch } from "../documents/documentUtils";
import type { ContractFilterCounts, ContractViewFilter } from "./types";

export const filterContracts = (
  contracts: Contract[],
  filter: ContractViewFilter,
  searchQuery: string,
): Contract[] =>
  contracts.filter(
    (contract) =>
      matchesDocumentSearch(contract, searchQuery) &&
      (filter === "all" || getContractState(contract).key === filter),
  );

export const getContractFilterCounts = (
  contracts: Contract[],
): ContractFilterCounts => ({
  all: contracts.length,
  attention: contracts.filter(
    (contract) => getContractState(contract).key === "attention",
  ).length,
  active: contracts.filter(
    (contract) => getContractState(contract).key === "active",
  ).length,
  expired: contracts.filter(
    (contract) => getContractState(contract).key === "expired",
  ).length,
});
