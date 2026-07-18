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
  activeContracts: ["contracts", "all"] as const,
  invoices: ["invoices"] as const,
  invoicesForList: (listId: number | null) => ["invoices", listId] as const,
  workspaceDocuments: ["workspace-documents"] as const,
  workspaceDocumentsForList: (listId: number | null) =>
    ["workspace-documents", listId] as const,
  protectedContracts: ["protected-contracts"] as const,
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
