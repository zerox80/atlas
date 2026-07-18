import React, { useState, useEffect } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { motion, AnimatePresence } from "framer-motion";
import { FiX, FiCheck, FiFolder } from "react-icons/fi";
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
  contract: Contract | null;
}

const AddToListModal: React.FC<AddToListModalProps> = ({
  isOpen,
  onClose,
  contract,
}) => {
  const queryClient = useQueryClient();
  const [contractLists, setContractLists] = useState<number[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const contractId = contract?.id ?? null;

  const { data: lists } = useQuery<ContractList[]>(
    queryKeys.lists,
    async () => {
      const res = await api.get<ContractList[]>("/lists");
      return res.data;
    },
    { enabled: isOpen },
  );

  useEffect(() => {
    if (!isOpen) return;
    setContractLists(contract?.lists?.map((list) => list.id) ?? []);
  }, [isOpen, contract]);

  const handleToggleList = async (listId: number) => {
    if (!contractId) return;
    setIsLoading(true);

    try {
      if (contractLists.includes(listId)) {
        // Remove from list
        await api.delete(`/lists/${listId}/contracts/${contractId}`);
        setContractLists((prev) => prev.filter((id) => id !== listId));
      } else {
        // Add to list
        await api.post(`/lists/${listId}/contracts/${contractId}`);
        setContractLists((prev) => [...prev, listId]);
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
                    Sammlungen zuweisen
                  </h3>
                  <p className="mt-1 max-w-[320px] truncate text-sm muted">
                    {contract?.title ?? ""}
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
                {lists && lists.length > 0 ? (
                  <div className="space-y-2">
                    {lists.map((list) => {
                      const isAssigned = contractLists.includes(list.id);
                      return (
                        <button
                          key={list.id}
                          onClick={() => handleToggleList(list.id)}
                          disabled={isLoading}
                          className={[
                            "flex w-full items-center gap-3 rounded-2xl border p-3.5 text-left",
                            "transition-all disabled:opacity-50",
                            isAssigned
                              ? "border-[#b8f15a]/25 bg-[#b8f15a]/[0.08]"
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
                            <p className="font-semibold text-white">
                              {list.name}
                            </p>
                            {list.description && (
                              <p className="truncate text-sm muted">
                                {list.description}
                              </p>
                            )}
                          </div>
                          <div className="flex items-center gap-2">
                            <span className="text-xs muted">
                              {list.contract_count} Verträge
                            </span>
                            {isAssigned && (
                              <div className="flex h-6 w-6 items-center justify-center rounded-full bg-[#b8f15a]">
                                <FiCheck size={14} className="text-[#111700]" />
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
                      Noch keine Sammlungen
                    </p>
                    <p className="mt-1 text-sm muted">
                      Erstelle zuerst eine Sammlung im Bereich „Sammlungen“.
                    </p>
                  </div>
                )}
              </div>

              <div className="border-t border-white/[0.07] p-4">
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
