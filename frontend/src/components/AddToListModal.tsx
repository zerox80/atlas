import React, { useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { motion, AnimatePresence } from "framer-motion";
import { FiX, FiCheck, FiFolder, FiHome, FiMinus } from "react-icons/fi";
import api from "../api";
import type { Contract, ContractList } from "../types";
import { getApiErrorMessage } from "../utils/errorUtils";
import {
  invalidateListAndDocumentQueries,
  queryKeys,
} from "../queryKeys";

interface AddToListModalProps {
  isOpen: boolean;
  onClose: () => void;
  contract?: Contract | null;
  contracts?: Contract[];
}

interface ListAssignmentResponse {
  list_ids: number[];
}

interface BulkListAssignmentResponse {
  assignments: Array<{
    contract_id: number;
    list_ids: number[];
  }>;
  changed_count: number;
  operation: "add" | "remove" | "move_to_default";
}

const AddToListModal: React.FC<AddToListModalProps> = ({
  isOpen,
  onClose,
  contract,
  contracts,
}) => {
  const queryClient = useQueryClient();
  const activeContracts = useMemo(
    () => (contracts?.length ? contracts : contract ? [contract] : []),
    [contract, contracts],
  );
  const contractIds = useMemo(
    () => activeContracts.map((item) => item.id),
    [activeContracts],
  );
  const selectedDocumentLabel = useMemo(() => {
    const invoicesOnly = activeContracts.every(
      (item) => item.document_type === "invoice",
    );
    const contractsOnly = activeContracts.every(
      (item) => item.document_type === "contract",
    );

    if (invoicesOnly) return "Rechnungen";
    if (contractsOnly) return "Verträge";
    return "Dokumente";
  }, [activeContracts]);
  const [contractLists, setContractLists] = useState<
    Record<number, number[]>
  >({});
  const [isLoading, setIsLoading] = useState(false);

  const { data: lists, isLoading: areListsLoading } = useQuery<ContractList[]>(
    queryKeys.lists,
    async () => {
      const res = await api.get<ContractList[]>("/lists");
      return res.data;
    },
    { enabled: isOpen },
  );

  useEffect(() => {
    if (!isOpen) return;
    setContractLists(
      Object.fromEntries(
        activeContracts.map((item) => [
          item.id,
          item.lists?.map((list) => list.id) ?? [],
        ]),
      ),
    );
  }, [activeContracts, isOpen]);

  const assignableLists = useMemo(
    () => lists?.filter((list) => !list.is_default) ?? [],
    [lists],
  );
  const defaultListIds = useMemo(
    () =>
      new Set(
        [...(lists ?? []), ...activeContracts.flatMap((item) => item.lists ?? [])]
          .filter((list) => list.is_default)
          .map((list) => list.id),
      ),
    [activeContracts, lists],
  );
  const allInPersonalDefault =
    contractIds.length > 0 &&
    contractIds.every((contractId) => {
      const assignedListIds = contractLists[contractId] ?? [];
      return (
        assignedListIds.length === 1 &&
        defaultListIds.has(assignedListIds[0])
      );
    });

  const handleMoveToPersonalDefault = async () => {
    if (!contractIds.length || allInPersonalDefault) return;
    setIsLoading(true);

    try {
      const response = await api.post<BulkListAssignmentResponse>(
        "/contract-list-assignments/personal-default",
        { contract_ids: contractIds },
      );
      setContractLists(
        Object.fromEntries(
          response.data.assignments.map((assignment) => [
            assignment.contract_id,
            assignment.list_ids,
          ]),
        ),
      );
      await invalidateListAndDocumentQueries(queryClient);
    } catch (error: unknown) {
      alert(
        getApiErrorMessage(
          error,
          "Fehler beim Verschieben in den persönlichen Workspace",
        ),
      );
    } finally {
      setIsLoading(false);
    }
  };

  const handleToggleList = async (listId: number) => {
    if (!contractIds.length) return;
    setIsLoading(true);

    try {
      const assignedCount = contractIds.filter((contractId) =>
        contractLists[contractId]?.includes(listId),
      ).length;
      const operation =
        assignedCount === contractIds.length ? "remove" : "add";

      if (contractIds.length === 1) {
        const contractId = contractIds[0];
        if (!contractId) return;
        const response =
          operation === "remove"
            ? await api.delete<ListAssignmentResponse>(
                `/lists/${listId}/contracts/${contractId}`,
              )
            : await api.post<ListAssignmentResponse>(
                `/lists/${listId}/contracts/${contractId}`,
              );
        setContractLists({ [contractId]: response.data.list_ids });
      } else {
        const response = await api.post<BulkListAssignmentResponse>(
          `/lists/${listId}/contract-assignments`,
          { contract_ids: contractIds, operation },
        );
        setContractLists(
          Object.fromEntries(
            response.data.assignments.map((assignment) => [
              assignment.contract_id,
              assignment.list_ids,
            ]),
          ),
        );
      }
      await invalidateListAndDocumentQueries(queryClient);
    } catch (error: unknown) {
      alert(
        getApiErrorMessage(
          error,
          "Fehler beim Aktualisieren der Listenzuweisung",
        ),
      );
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <AnimatePresence>
      {isOpen && (
        <>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-40 bg-[#05070b]/80 backdrop-blur-md"
            onClick={onClose}
          />
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: 20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 20 }}
            className="fixed inset-0 z-50 flex items-center justify-center p-4 pointer-events-none"
          >
            <div className="surface-raised pointer-events-auto w-full max-w-lg overflow-hidden">
              <div className="flex items-start justify-between border-b border-white/[0.07] p-6">
                <div>
                  <p className="eyebrow">Organisation</p>
                  <h3 className="mt-2 text-xl font-semibold text-white">
                    Workspaces verwalten
                  </h3>
                  <p className="mt-1 max-w-[320px] truncate text-sm muted">
                    {activeContracts.length === 1
                      ? (activeContracts[0]?.title ?? "")
                      : `${activeContracts.length} ${selectedDocumentLabel} ausgewählt`}
                  </p>
                </div>
                <button
                  onClick={onClose}
                  className="icon-btn"
                  aria-label="Dialog schließen"
                >
                  <FiX size={19} />
                </button>
              </div>

              <div className="max-h-[430px] overflow-y-auto p-4 sm:p-6">
                {activeContracts.length > 1 && (
                  <p className="mb-4 rounded-xl border border-white/[0.07] bg-white/[0.025] p-3 text-xs leading-5 muted">
                    Bei einer gemischten Auswahl wird der Workspace beim
                    Anklicken allen ausgewählten Dokumenten hinzugefügt. Sind
                    bereits alle enthalten, entfernt der Klick sie gemeinsam.
                  </p>
                )}
                <button
                  type="button"
                  onClick={() => void handleMoveToPersonalDefault()}
                  disabled={isLoading || allInPersonalDefault}
                  className={[
                    "flex w-full items-center gap-3 rounded-2xl border p-3.5 text-left transition-all",
                    "disabled:cursor-default",
                    allInPersonalDefault
                      ? "border-[#b8f15a]/25 bg-[#b8f15a]/[0.08]"
                      : "border-[#77a7ff]/25 bg-[#77a7ff]/[0.07] hover:border-[#77a7ff]/45 hover:bg-[#77a7ff]/[0.11]",
                  ].join(" ")}
                >
                  <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[#77a7ff]/15 text-[#9dbdff]">
                    <FiHome size={19} />
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="font-semibold text-white">
                      Persönlicher Workspace
                    </p>
                    <p className="mt-0.5 text-xs leading-5 muted">
                      {activeContracts.length > 1
                        ? "Jedes Dokument kommt in den persönlichen Workspace seines Eigentümers."
                        : "Entfernt das Dokument aus allen Team-Workspaces."}
                    </p>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    <span className="text-xs font-semibold text-[#b9cced]">
                      {allInPersonalDefault
                        ? "Bereits dort"
                        : "Hierhin verschieben"}
                    </span>
                    {allInPersonalDefault && (
                      <div className="flex h-6 w-6 items-center justify-center rounded-full bg-[#b8f15a] text-[#111700]">
                        <FiCheck size={14} />
                      </div>
                    )}
                  </div>
                </button>

                <div className="my-5 flex items-center gap-3">
                  <div className="h-px flex-1 bg-white/[0.07]" />
                  <span className="text-[11px] font-semibold uppercase tracking-[0.16em] muted">
                    Team-Workspaces
                  </span>
                  <div className="h-px flex-1 bg-white/[0.07]" />
                </div>

                {areListsLoading ? (
                  <div className="py-10 text-center text-sm muted">
                    Workspaces werden geladen…
                  </div>
                ) : assignableLists.length > 0 ? (
                  <div className="space-y-2">
                    {assignableLists.map((list) => {
                      const assignedCount = contractIds.filter((contractId) =>
                        contractLists[contractId]?.includes(list.id),
                      ).length;
                      const isAssigned =
                        contractIds.length > 0 &&
                        assignedCount === contractIds.length;
                      const isPartlyAssigned =
                        assignedCount > 0 && !isAssigned;
                      return (
                        <button
                          key={list.id}
                          onClick={() => void handleToggleList(list.id)}
                          disabled={isLoading}
                          className={[
                            "flex w-full items-center gap-3 rounded-2xl border p-3.5 text-left",
                            "transition-all disabled:opacity-50",
                            isAssigned
                              ? "border-[#b8f15a]/25 bg-[#b8f15a]/[0.08]"
                              : isPartlyAssigned
                                ? "border-[#77a7ff]/25 bg-[#77a7ff]/[0.07]"
                                : "border-white/[0.07] bg-white/[0.025] hover:border-white/[0.14] hover:bg-white/[0.045]",
                          ].join(" ")}
                        >
                          <div
                            className="p-2 rounded-lg flex-shrink-0"
                            style={{ backgroundColor: `${list.color}30` }}
                          >
                            <FiFolder size={18} style={{ color: list.color }} />
                          </div>
                          <div className="flex-1 text-left">
                            <div className="flex flex-wrap items-center gap-2">
                              <p className="font-semibold text-white">
                                {list.name}
                              </p>
                              {list.is_preferred_default && (
                                <span className="chip">Dein Standard</span>
                              )}
                            </div>
                            {list.owner_username && (
                              <p className="text-xs muted">
                                Eigentümer: {list.owner_username}
                              </p>
                            )}
                            {list.description && (
                              <p className="truncate text-sm muted">
                                {list.description}
                              </p>
                            )}
                          </div>
                          <div className="flex items-center gap-2">
                            <span className="text-xs muted">
                              {activeContracts.length > 1
                                ? `${assignedCount}/${activeContracts.length} ausgewählt`
                                : `${list.contract_count} Dokumente`}
                            </span>
                            {(isAssigned || isPartlyAssigned) && (
                              <div
                                className={[
                                  "flex h-6 w-6 items-center justify-center rounded-full",
                                  isAssigned
                                    ? "bg-[#b8f15a] text-[#111700]"
                                    : "bg-[#77a7ff] text-[#07111f]",
                                ].join(" ")}
                              >
                                {isAssigned ? (
                                  <FiCheck size={14} />
                                ) : (
                                  <FiMinus size={14} />
                                )}
                              </div>
                            )}
                          </div>
                        </button>
                      );
                    })}
                  </div>
                ) : (
                  <div className="py-10 text-center">
                    <FiFolder
                      size={42}
                      className="mx-auto mb-3 text-[#596474]"
                    />
                    <p className="font-semibold text-white">
                      Keine weiteren Team-Workspaces
                    </p>
                    <p className="mt-1 text-sm muted">
                      Der persönliche Workspace steht als sicheres Ziel oben
                      bereit.
                    </p>
                  </div>
                )}
              </div>

              <div className="border-t border-white/[0.07] p-4">
                <p className="mb-3 text-center text-xs muted">
                  Den Inhalt eines Workspace öffnest du jederzeit über den
                  Workspace-Wechsler oben links.
                </p>
                <button onClick={onClose} className="btn-secondary w-full">
                  Schließen
                </button>
              </div>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
};

export default AddToListModal;
