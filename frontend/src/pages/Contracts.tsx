import React, { useMemo, useState } from "react";
import { useInfiniteQuery, useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { FiFileText, FiPlus } from "react-icons/fi";
import api, {
  fetchContractPage,
  type ContractCursor,
  toggleContractProtection,
} from "../api";
import { useUser } from "../App";
import { EmptyState, LoadingState, PageHeader } from "../components/ui";
import ContractCard from "../features/contracts/ContractCard";
import ContractModals from "../features/contracts/ContractModals";
import ContractToolbar from "../features/contracts/ContractToolbar";
import type { ContractViewFilter } from "../features/contracts/types";
import { downloadDocument } from "../features/documents/downloadDocument";
import { getListIdFromSearchParams } from "../features/documents/documentUtils";
import { invalidateDocumentQueries, invalidateListAndDocumentQueries, queryKeys } from "../queryKeys";
import { useDebouncedValue } from "../hooks/useDebouncedValue";
import type { Contract, ContractPage } from "../types";

const Contracts: React.FC = () => {
  const { isAdmin } = useUser();
  const queryClient = useQueryClient();
  const [searchParams] = useSearchParams();
  const listId = getListIdFromSearchParams(searchParams);
  const [isUploadOpen, setIsUploadOpen] = useState(false);
  const [editingContract, setEditingContract] = useState<Contract | null>(null);
  const [chatContract, setChatContract] = useState<Contract | null>(null);
  const [listContract, setListContract] = useState<Contract | null>(null);
  const [auditContract, setAuditContract] = useState<Contract | null>(null);
  const [detailsContract, setDetailsContract] = useState<Contract | null>(null);
  const [filter, setFilter] = useState<ContractViewFilter>("all");
  const [search, setSearch] = useState("");
  const [openMenu, setOpenMenu] = useState<number | null>(null);

  const debouncedSearch = useDebouncedValue(search.trim());
  const {
    data: contractPages,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
    isError,
    isLoading,
  } = useInfiniteQuery<ContractPage, unknown>(
    queryKeys.contractPage(listId, filter, debouncedSearch),
    ({ pageParam }) =>
      fetchContractPage(
        {
          document_type: "contract",
          limit: 40,
          ...(debouncedSearch ? { q: debouncedSearch } : {}),
          ...(filter !== "all" ? { state: filter } : {}),
          ...(listId ? { list_id: listId } : {}),
        },
        pageParam as ContractCursor | undefined,
      ),
    {
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
    () => contractPages?.pages.flatMap((page) => page.items) ?? [],
    [contractPages],
  );
  const counts = contractPages?.pages[0]?.summary ?? {
    all: 0,
    attention: 0,
    active: 0,
    expired: 0,
  };

  const openUpload = (contract: Contract | null = null) => {
    setEditingContract(contract);
    setIsUploadOpen(true);
    setOpenMenu(null);
  };

  const handleDelete = async (contract: Contract) => {
    setOpenMenu(null);
    if (contract.version === undefined) {
      alert("Die Dokumentversion fehlt. Bitte lade die Ansicht neu.");
      return;
    }
    if (contract.is_protected) {
      alert(
        "Dieser Vertrag ist geschützt. Bitte heben Sie zuerst den Schutz auf.",
      );
      return;
    }
    if (!window.confirm(`Möchten Sie den Vertrag „${contract.title}“ wirklich löschen?`)) {
      return;
    }

    try {
      await api.delete(`/contracts/${contract.id}`, {
        params: { version: contract.version },
      });
      await invalidateListAndDocumentQueries(queryClient);
    } catch {
      alert("Der Vertrag konnte nicht gelöscht werden.");
    }
  };

  const handleDownload = async (contract: Contract) => {
    try {
      await downloadDocument(contract);
    } catch {
      alert("Das Dokument konnte nicht heruntergeladen werden.");
    }
  };

  const handleProtection = async (contract: Contract) => {
    setOpenMenu(null);
    if (contract.version === undefined) {
      alert("Die Dokumentversion fehlt. Bitte lade die Ansicht neu.");
      return;
    }
    try {
      await toggleContractProtection(contract.id, contract.version);
      await invalidateDocumentQueries(queryClient);
    } catch {
      alert("Der Schutzstatus konnte nicht geändert werden.");
    }
  };

  const handleDetailsEdit = (contract: Contract) => {
    setDetailsContract(null);
    openUpload(contract);
  };

  if (isLoading) return <LoadingState label="Verträge werden geladen" />;
  if (isError)
    return (
      <div className="app-page">
        <EmptyState
          icon={FiFileText}
          title="Verträge konnten nicht geladen werden"
          description="Bitte versuche es erneut."
        />
      </div>
    );

  return (
    <div className="app-page">
      <PageHeader
        eyebrow="Contract Operations"
        title="Verträge & Fristen"
        description="Eine fokussierte Arbeitsansicht für Laufzeiten, Kündigungsfenster und Vertragswerte."
        actions={
          <button onClick={() => openUpload()} className="btn-primary">
            <FiPlus /> Vertrag hinzufügen
          </button>
        }
      />

      <ContractToolbar
        counts={counts}
        filter={filter}
        onFilterChange={setFilter}
        searchQuery={search}
        onSearchChange={setSearch}
      />

      {contracts.length ? (
        <div className="grid gap-4 xl:grid-cols-2">
          {contracts.map((contract) => (
            <ContractCard
              key={contract.id}
              contract={contract}
              isAdmin={isAdmin}
              isMenuOpen={openMenu === contract.id}
              onAssignToList={(selectedContract) => {
                setListContract(selectedContract);
                setOpenMenu(null);
              }}
              onDelete={handleDelete}
              onDownload={handleDownload}
              onEdit={openUpload}
              onOpenAudit={(selectedContract) => {
                setAuditContract(selectedContract);
                setOpenMenu(null);
              }}
              onOpenChat={setChatContract}
              onOpenDetails={setDetailsContract}
              onToggleMenu={() =>
                setOpenMenu(
                  openMenu === contract.id ? null : contract.id,
                )
              }
              onToggleProtection={handleProtection}
            />
          ))}
        </div>
      ) : (
        <EmptyState
          icon={FiFileText}
          title={
            search || filter !== "all"
              ? "Keine passenden Verträge"
              : "Noch keine Verträge"
          }
          description={
            search || filter !== "all"
              ? "Passe Suche oder Filter an, um andere Ergebnisse zu sehen."
              : "Lade den ersten Vertrag hoch und lass Fristen automatisch erkennen."
          }
          action={
            !search && filter === "all" ? (
              <button onClick={() => openUpload()} className="btn-primary">
                <FiPlus /> Ersten Vertrag hochladen
              </button>
            ) : undefined
          }
        />
      )}

      {hasNextPage && (
        <div className="mt-5 flex justify-center">
          <button
            className="btn-secondary"
            disabled={isFetchingNextPage}
            onClick={() => void fetchNextPage()}
          >
            {isFetchingNextPage ? "Weitere Verträge werden geladen…" : "Mehr Verträge laden"}
          </button>
        </div>
      )}

      <ContractModals
        auditContract={auditContract}
        chatContract={chatContract}
        detailsContract={detailsContract}
        editingContract={editingContract}
        isUploadOpen={isUploadOpen}
        listContract={listContract}
        onAuditClose={() => setAuditContract(null)}
        onChatClose={() => setChatContract(null)}
        onDetailsClose={() => setDetailsContract(null)}
        onDownload={handleDownload}
        onEdit={handleDetailsEdit}
        onListClose={() => setListContract(null)}
        onUploadClose={() => {
          setIsUploadOpen(false);
          setEditingContract(null);
        }}
      />
    </div>
  );
};

export default Contracts;
