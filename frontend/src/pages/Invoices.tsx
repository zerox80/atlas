import React, { useMemo, useState } from "react";
import { useInfiniteQuery, useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { FiFileText, FiPlus } from "react-icons/fi";
import api, { fetchContractPage, type ContractCursor } from "../api";
import { useUser } from "../App";
import UploadModal from "../components/UploadModal";
import { EmptyState, LoadingState, PageHeader } from "../components/ui";
import InvoiceArchive from "../features/invoices/InvoiceArchive";
import InvoiceStats from "../features/invoices/InvoiceStats";
import { downloadDocument } from "../features/documents/downloadDocument";
import { getListIdFromSearchParams } from "../features/documents/documentUtils";
import { invalidateListAndDocumentQueries, queryKeys } from "../queryKeys";
import { useDebouncedValue } from "../hooks/useDebouncedValue";
import type { Contract, ContractPage } from "../types";

const Invoices: React.FC = () => {
  const { user } = useUser();
  const queryClient = useQueryClient();
  const [searchParams] = useSearchParams();
  const listId = getListIdFromSearchParams(searchParams);
  const [isUploadOpen, setIsUploadOpen] = useState(false);
  const [editingInvoice, setEditingInvoice] = useState<Contract | null>(null);
  const [search, setSearch] = useState("");

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
  const summary = invoicePages?.pages[0]?.summary;
  const stats = {
    total: summary?.total_value ?? 0,
    currentMonthTotal: summary?.current_month_value ?? 0,
  };

  const openUpload = (invoice: Contract | null = null) => {
    setEditingInvoice(invoice);
    setIsUploadOpen(true);
  };

  const handleDelete = async (invoice: Contract) => {
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
          user?.can_create_documents ? (
            <button onClick={() => openUpload()} className="btn-primary">
              <FiPlus /> Rechnung hochladen
            </button>
          ) : undefined
        }
      />

      <InvoiceStats invoiceCount={summary?.all ?? 0} stats={stats} />
      <InvoiceArchive
        invoices={invoices}
        onCreate={
          user?.can_create_documents ? () => openUpload() : undefined
        }
        onDelete={handleDelete}
        onDownload={handleDownload}
        onEdit={openUpload}
        onSearchChange={setSearch}
        searchQuery={search}
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
    </div>
  );
};

export default Invoices;
