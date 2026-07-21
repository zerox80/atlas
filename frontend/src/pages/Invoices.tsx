import React, { useEffect, useMemo, useState } from "react";
import { useInfiniteQuery, useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import {
  FiCheckSquare,
  FiFileText,
  FiFolder,
  FiPlus,
  FiX,
} from "react-icons/fi";
import api, { fetchContractPage, type ContractCursor } from "../api";
import { useUser } from "../App";
import UploadModal from "../components/UploadModal";
import AddToListModal from "../components/AddToListModal";
import { EmptyState, LoadingState, PageHeader } from "../components/ui";
import InvoiceArchive from "../features/invoices/InvoiceArchive";
import InvoiceStats from "../features/invoices/InvoiceStats";
import { downloadDocument } from "../features/documents/downloadDocument";
import { getListIdFromSearchParams } from "../features/documents/documentUtils";
import { invalidateListAndDocumentQueries, queryKeys } from "../queryKeys";
import { useDebouncedValue } from "../hooks/useDebouncedValue";
import type { Contract, ContractPage } from "../types";

const Invoices: React.FC = () => {
  const { isAdmin, user } = useUser();
  const queryClient = useQueryClient();
  const [searchParams] = useSearchParams();
  const listId = getListIdFromSearchParams(searchParams);
  const [isUploadOpen, setIsUploadOpen] = useState(false);
  const [editingInvoice, setEditingInvoice] = useState<Contract | null>(null);
  const [listInvoices, setListInvoices] = useState<Contract[]>([]);
  const [search, setSearch] = useState("");
  const [openMenu, setOpenMenu] = useState<number | null>(null);
  const [isSelectionMode, setIsSelectionMode] = useState(false);
  const [selectedInvoiceIds, setSelectedInvoiceIds] = useState<Set<number>>(
    () => new Set(),
  );

  const debouncedSearch = useDebouncedValue(search.trim());
  const {
    data: invoicePages,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
    isError,
    isLoading,
  } = useInfiniteQuery<ContractPage, unknown>(
    queryKeys.invoicePage(listId, debouncedSearch),
    ({ pageParam }) =>
      fetchContractPage(
        {
          document_type: "invoice",
          limit: 50,
          ...(debouncedSearch ? { q: debouncedSearch } : {}),
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

  const invoices = useMemo(
    () => invoicePages?.pages.flatMap((page) => page.items) ?? [],
    [invoicePages],
  );
  const selectedInvoices = useMemo(
    () => invoices.filter((invoice) => selectedInvoiceIds.has(invoice.id)),
    [invoices, selectedInvoiceIds],
  );
  const allVisibleSelected =
    invoices.length > 0 &&
    invoices.every((invoice) => selectedInvoiceIds.has(invoice.id));
  const summary = invoicePages?.pages[0]?.summary;
  const stats = {
    total: summary?.total_value ?? 0,
    currentMonthTotal: summary?.current_month_value ?? 0,
  };

  const stopSelection = () => {
    setIsSelectionMode(false);
    setSelectedInvoiceIds(new Set());
  };

  useEffect(() => {
    setIsSelectionMode(false);
    setSelectedInvoiceIds(new Set());
    setOpenMenu(null);
  }, [listId]);

  const toggleInvoiceSelection = (invoice: Contract) => {
    setSelectedInvoiceIds((current) => {
      const next = new Set(current);
      if (next.has(invoice.id)) next.delete(invoice.id);
      else next.add(invoice.id);
      return next;
    });
  };

  const toggleAllVisible = () => {
    setSelectedInvoiceIds((current) => {
      const next = new Set(current);
      if (allVisibleSelected) {
        invoices.forEach((invoice) => next.delete(invoice.id));
      } else {
        invoices.forEach((invoice) => next.add(invoice.id));
      }
      return next;
    });
  };

  const openUpload = (invoice: Contract | null = null) => {
    setEditingInvoice(invoice);
    setIsUploadOpen(true);
    setOpenMenu(null);
  };

  const handleDelete = async (invoice: Contract) => {
    setOpenMenu(null);
    if (invoice.version === undefined) {
      alert("Die Dokumentversion fehlt. Bitte lade die Ansicht neu.");
      return;
    }
    if (invoice.is_protected) {
      alert(
        "Diese Rechnung ist geschützt. Bitte heben Sie zuerst den Schutz auf.",
      );
      return;
    }
    if (!window.confirm(`Möchten Sie die Rechnung „${invoice.title}“ wirklich löschen?`)) {
      return;
    }

    try {
      await api.delete(`/contracts/${invoice.id}`, {
        params: { version: invoice.version },
      });
      await invalidateListAndDocumentQueries(queryClient);
    } catch {
      alert("Die Rechnung konnte nicht gelöscht werden.");
    }
  };

  const handleDownload = async (invoice: Contract) => {
    try {
      await downloadDocument(invoice);
    } catch {
      alert("Die Rechnung konnte nicht heruntergeladen werden.");
    }
  };

  if (isLoading) return <LoadingState label="Rechnungen werden geladen" />;
  if (isError)
    return (
      <div className="app-page">
        <EmptyState
          icon={FiFileText}
          title="Rechnungen konnten nicht geladen werden"
          description="Bitte versuche es erneut."
        />
      </div>
    );

  return (
    <div className="app-page">
      <PageHeader
        eyebrow="Invoice Desk"
        title="Rechnungen"
        description="Ein schneller, eigenständiger Ablageprozess für Rechnungen – auch wenn kein Vertrag existiert."
        actions={
          isAdmin || user?.can_create_documents ? (
            <div className="flex flex-wrap items-center gap-2">
              {isAdmin && invoices.length > 0 && (
                <button
                  onClick={() => {
                    if (isSelectionMode) stopSelection();
                    else {
                      setIsSelectionMode(true);
                      setOpenMenu(null);
                    }
                  }}
                  className="btn-secondary"
                >
                  {isSelectionMode ? <FiX /> : <FiCheckSquare />}
                  {isSelectionMode ? "Auswahl schließen" : "Auswählen"}
                </button>
              )}
              {user?.can_create_documents && (
                <button onClick={() => openUpload()} className="btn-primary">
                  <FiPlus /> Rechnung hochladen
                </button>
              )}
            </div>
          ) : undefined
        }
      />

      <InvoiceStats invoiceCount={summary?.all ?? 0} stats={stats} />

      {isAdmin && isSelectionMode && invoices.length > 0 && (
        <div className="surface mb-5 flex flex-col gap-3 p-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex flex-wrap items-center gap-3">
            <button onClick={toggleAllVisible} className="btn-secondary">
              <FiCheckSquare />
              {allVisibleSelected
                ? "Alle angezeigten abwählen"
                : "Alle angezeigten auswählen"}
            </button>
            <span className="text-sm font-semibold text-white">
              {selectedInvoices.length} von {invoices.length} angezeigten
              Rechnungen ausgewählt
            </span>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              onClick={() => setListInvoices(selectedInvoices)}
              disabled={selectedInvoices.length === 0}
              className="btn-primary disabled:cursor-not-allowed disabled:opacity-40"
            >
              <FiFolder /> Workspaces verwalten
            </button>
            <button onClick={stopSelection} className="btn-ghost">
              Abbrechen
            </button>
          </div>
        </div>
      )}

      <InvoiceArchive
        invoices={invoices}
        isAdmin={isAdmin}
        isSelectionMode={isSelectionMode}
        onAssignToList={(invoice) => {
          setListInvoices([invoice]);
          setOpenMenu(null);
        }}
        onCreate={
          user?.can_create_documents ? () => openUpload() : undefined
        }
        onDelete={handleDelete}
        onDownload={handleDownload}
        onEdit={openUpload}
        onSearchChange={(nextSearch) => {
          setSearch(nextSearch);
          stopSelection();
        }}
        onToggleMenu={(invoiceId) =>
          setOpenMenu(openMenu === invoiceId ? null : invoiceId)
        }
        onToggleSelection={toggleInvoiceSelection}
        openMenuId={openMenu}
        searchQuery={search}
        selectedInvoiceIds={selectedInvoiceIds}
      />

      {hasNextPage && (
        <div className="mt-5 flex justify-center">
          <button
            className="btn-secondary"
            disabled={isFetchingNextPage}
            onClick={() => void fetchNextPage()}
          >
            {isFetchingNextPage
              ? "Weitere Rechnungen werden geladen…"
              : "Mehr Rechnungen laden"}
          </button>
        </div>
      )}

      <UploadModal
        isOpen={isUploadOpen}
        onClose={() => {
          setIsUploadOpen(false);
          setEditingInvoice(null);
        }}
        initialData={editingInvoice}
        initialListId={listId}
        documentType="invoice"
      />
      <AddToListModal
        isOpen={listInvoices.length > 0}
        onClose={() => setListInvoices([])}
        contracts={listInvoices}
      />
    </div>
  );
};

export default Invoices;
