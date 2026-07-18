import type { QueryClient } from "@tanstack/react-query";

/**
 * Shared React Query key prefixes.
 *
 * Keep mutation invalidation at the resource level so that filtered variants
 * (for example a collection-specific contract list) are refreshed as well.
 */
export const queryKeys = {
  contracts: ["contracts"] as const,
  contractsForList: (listId: number | null) => ["contracts", listId] as const,
  contractPage: (listId: number | null, state: string, query: string) =>
    ["contracts", "page", listId, state, query] as const,
  contractOptions: (query: string) =>
    ["contracts", "options", query] as const,
  calendar: (start: string, end: string) =>
    ["contracts", "calendar", start, end] as const,
  invoices: ["invoices"] as const,
  invoicesForList: (listId: number | null) => ["invoices", listId] as const,
  invoicePage: (listId: number | null, query: string) =>
    ["invoices", "page", listId, query] as const,
  workspaceDocuments: ["workspace-documents"] as const,
  workspaceDocumentsForList: (listId: number | null) =>
    ["workspace-documents", listId] as const,
  dashboard: (listId: number | null) =>
    ["workspace-documents", "dashboard", listId] as const,
  protectedContracts: ["protected-contracts"] as const,
  protectedContractPage: ["protected-contracts", "page"] as const,
  lists: ["lists"] as const,
  tags: ["tags"] as const,
};

export const invalidateDocumentQueries = (queryClient: QueryClient) =>
  Promise.all([
    queryClient.invalidateQueries(queryKeys.contracts),
    queryClient.invalidateQueries(queryKeys.invoices),
    queryClient.invalidateQueries(queryKeys.workspaceDocuments),
    queryClient.invalidateQueries(queryKeys.protectedContracts),
  ]);

export const invalidateDocumentAndTagQueries = (queryClient: QueryClient) =>
  Promise.all([
    invalidateDocumentQueries(queryClient),
    queryClient.invalidateQueries(queryKeys.tags),
  ]);

export const invalidateListAndDocumentQueries = (queryClient: QueryClient) =>
  Promise.all([
    queryClient.invalidateQueries(queryKeys.lists),
    invalidateDocumentQueries(queryClient),
  ]);
