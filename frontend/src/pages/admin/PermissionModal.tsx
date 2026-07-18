import React, { useEffect, useMemo, useState } from "react";
import { useInfiniteQuery } from "@tanstack/react-query";
import { fetchContractPage, type ContractCursor } from "../../api";
import { useDebouncedValue } from "../../hooks/useDebouncedValue";
import { queryKeys } from "../../queryKeys";
import type { ContractPage } from "../../types";
import ModalFrame from "./ModalFrame";
import type { User } from "./types";

interface PermissionModalProps {
  isOpen: boolean;
  level: string;
  onClose: () => void;
  onSubmit: React.FormEventHandler<HTMLFormElement>;
  setContractId: (value: number) => void;
  setLevel: (value: string) => void;
  setUserId: (value: number) => void;
  contractId: number;
  userId: number;
  users: User[];
}

const PermissionModal: React.FC<PermissionModalProps> = ({
  contractId,
  isOpen,
  level,
  onClose,
  onSubmit,
  setContractId,
  setLevel,
  setUserId,
  userId,
  users,
}) => {
  const [contractSearch, setContractSearch] = useState("");
  const debouncedSearch = useDebouncedValue(contractSearch.trim());
  const {
    data,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
    isLoading: isFetching,
    isError,
  } = useInfiniteQuery<ContractPage, unknown>(
    queryKeys.contractOptions(debouncedSearch),
    ({ pageParam }) =>
      fetchContractPage(
        {
          include_summary: false,
          limit: 50,
          ...(debouncedSearch ? { q: debouncedSearch } : {}),
        },
        pageParam as ContractCursor | undefined,
      ),
    {
      enabled: isOpen,
      getNextPageParam: (lastPage) =>
        lastPage.has_more &&
        lastPage.next_cursor_uploaded_at &&
        lastPage.next_cursor_id
          ? {
              uploadedAt: lastPage.next_cursor_uploaded_at,
              id: lastPage.next_cursor_id,
            }
          : undefined,
    },
  );
  const contracts = useMemo(
    () => data?.pages.flatMap((page) => page.items) ?? [],
    [data],
  );

  useEffect(() => {
    if (!isOpen) setContractSearch("");
  }, [isOpen]);

  useEffect(() => {
    if (contractId !== 0 && !contracts.some((contract) => contract.id === contractId)) {
      setContractId(0);
    }
  }, [contractId, contracts, setContractId]);

  return (
    <ModalFrame isOpen={isOpen} onClose={onClose}>
    <h2 className="mb-4 text-xl font-bold text-white">
      Berechtigung hinzufügen
    </h2>
    <form onSubmit={onSubmit} className="space-y-4">
      <div>
        <label className="mb-1 block text-sm font-medium text-gray-400">
          Benutzer
        </label>
        <select
          value={userId}
          onChange={(event) => setUserId(Number(event.target.value))}
          className={[
            "w-full rounded-lg border border-gray-700 bg-gray-800 px-4 py-2",
            "text-white focus:border-blue-500 focus:outline-none",
          ].join(" ")}
          required
        >
          <option value={0}>Benutzer wählen...</option>
          {users
            .filter((user) => user.role !== "admin" && user.is_active)
            .map((user) => (
              <option key={user.id} value={user.id}>
                {user.username}
              </option>
            ))}
        </select>
      </div>
      <div>
        <label className="mb-1 block text-sm font-medium text-gray-400">
          Vertrag
        </label>
        <input
          value={contractSearch}
          maxLength={200}
          onChange={(event) => {
            setContractId(0);
            setContractSearch(event.target.value);
          }}
          className="mb-2 w-full rounded-lg border border-gray-700 bg-gray-800 px-4 py-2 text-white focus:border-blue-500 focus:outline-none"
          placeholder="Dokument suchen…"
          type="search"
        />
        <select
          value={contractId || ""}
          onChange={(event) => setContractId(Number(event.target.value))}
          className={[
            "w-full rounded-lg border border-gray-700 bg-gray-800 px-4 py-2",
            "text-white focus:border-blue-500 focus:outline-none",
          ].join(" ")}
          required
        >
          <option value="">
            {isFetching ? "Dokumente werden geladen…" : "Dokument wählen..."}
          </option>
          {contracts.map((contract) => (
            <option key={contract.id} value={contract.id}>
              {contract.title}
            </option>
          ))}
        </select>
        {isError && (
          <p className="mt-2 text-sm text-red-300" role="alert">
            Laden der Dokumente fehlgeschlagen.
          </p>
        )}
        {hasNextPage && (
          <button
            type="button"
            className="mt-2 w-full rounded-lg border border-gray-700 px-4 py-2 text-sm text-gray-300 transition-colors hover:bg-gray-800 disabled:cursor-not-allowed disabled:opacity-50"
            disabled={isFetchingNextPage}
            onClick={() => void fetchNextPage()}
          >
            {isFetchingNextPage ? "Weitere Dokumente werden geladen..." : "Mehr Dokumente laden"}
          </button>
        )}
      </div>
      <div>
        <label className="mb-1 block text-sm font-medium text-gray-400">
          Berechtigung
        </label>
        <select
          value={level}
          onChange={(event) => setLevel(event.target.value)}
          className={[
            "w-full rounded-lg border border-gray-700 bg-gray-800 px-4 py-2",
            "text-white focus:border-blue-500 focus:outline-none",
          ].join(" ")}
        >
          <option value="read">Nur Lesen</option>
          <option value="write">Bearbeiten</option>
          <option value="full">Vollzugriff (inkl. Löschen)</option>
        </select>
      </div>
      <div className="flex gap-3 pt-4">
        <button
          type="button"
          onClick={onClose}
          className="flex-1 rounded-lg bg-gray-700 px-4 py-2 text-white transition-colors hover:bg-gray-600"
        >
          Abbrechen
        </button>
        <button
          type="submit"
          disabled={userId === 0 || contractId === 0}
          className={[
            "flex-1 rounded-lg bg-blue-600 px-4 py-2 text-white transition-colors",
            "hover:bg-blue-500 disabled:cursor-not-allowed disabled:opacity-50",
          ].join(" ")}
        >
          Hinzufügen
        </button>
      </div>
    </form>
    </ModalFrame>
  );
};

export default PermissionModal;
