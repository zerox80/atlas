import React, { useEffect, useMemo, useState } from "react";
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import api, { fetchContractPage, type ContractCursor } from "../../api";
import { useDebouncedValue } from "../../hooks/useDebouncedValue";
import { queryKeys } from "../../queryKeys";
import type { ContractList, ContractPage } from "../../types";
import ModalFrame from "./ModalFrame";
import type { User } from "./types";

interface PermissionModalProps {
  isOpen: boolean;
  level: string;
  onClose: () => void;
  onSubmit: React.FormEventHandler<HTMLFormElement>;
  setContractId: (value: number) => void;
  setListId: (value: number) => void;
  setLevel: (value: string) => void;
  setScope: (value: "workspace" | "document") => void;
  setUserId: (value: number) => void;
  contractId: number;
  listId: number;
  scope: "workspace" | "document";
  userId: number;
  users: User[];
}

const PermissionModal: React.FC<PermissionModalProps> = ({
  contractId,
  isOpen,
  level,
  listId,
  onClose,
  onSubmit,
  setContractId,
  setListId,
  setLevel,
  setScope,
  setUserId,
  userId,
  users,
  scope,
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
      enabled: isOpen && scope === "document",
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
  const { data: workspaces = [], isLoading: workspacesLoading } = useQuery<
    ContractList[]
  >(
    queryKeys.lists,
    async () => (await api.get<ContractList[]>("/lists")).data,
    { enabled: isOpen },
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
          Gültigkeitsbereich
        </label>
        <select
          value={scope}
          onChange={(event) => {
            setScope(event.target.value as "workspace" | "document");
            setContractId(0);
            setListId(0);
          }}
          className={[
            "w-full rounded-lg border border-gray-700 bg-gray-800 px-4 py-2",
            "text-white focus:border-blue-500 focus:outline-none",
          ].join(" ")}
        >
          <option value="workspace">Gesamter Workspace</option>
          <option value="document">Einzelnes Dokument</option>
        </select>
      </div>
      {scope === "workspace" ? (
        <div>
          <label className="mb-1 block text-sm font-medium text-gray-400">
            Workspace
          </label>
          <select
            value={listId || ""}
            onChange={(event) => setListId(Number(event.target.value))}
            className="w-full rounded-lg border border-gray-700 bg-gray-800 px-4 py-2 text-white focus:border-blue-500 focus:outline-none"
            required
          >
            <option value="">
              {workspacesLoading
                ? "Workspaces werden geladen…"
                : "Workspace wählen..."}
            </option>
            {workspaces.map((workspace) => (
              <option key={workspace.id} value={workspace.id}>
                {workspace.name}
                {workspace.owner_username
                  ? ` · ${workspace.owner_username}`
                  : ""}
                {workspace.is_default ? " (persönlich)" : ""}
              </option>
            ))}
          </select>
          <p className="mt-2 text-xs leading-5 text-gray-500">
            Rechte ändern den Nutzer-Standard nicht automatisch. Den
            Standard-Workspace legst du separat unter „Benutzer bearbeiten“
            fest. Schreibrecht auf einem fremden persönlichen Default erlaubt
            das Bearbeiten dort, aber keine neuen Uploads hinein.
          </p>
        </div>
      ) : (
        <div>
          <label className="mb-1 block text-sm font-medium text-gray-400">
            Dokument
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
            className="w-full rounded-lg border border-gray-700 bg-gray-800 px-4 py-2 text-white focus:border-blue-500 focus:outline-none"
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
              {isFetchingNextPage
                ? "Weitere Dokumente werden geladen..."
                : "Mehr Dokumente laden"}
            </button>
          )}
        </div>
      )}
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
          disabled={
            userId === 0 ||
            (scope === "workspace" ? listId === 0 : contractId === 0)
          }
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
