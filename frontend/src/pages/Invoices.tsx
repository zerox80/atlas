import React, { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { FiPlus } from "react-icons/fi";
import api, { fetchAllContracts } from "../api";
import UploadModal from "../components/UploadModal";
import { LoadingState, PageHeader } from "../components/ui";
import InvoiceArchive from "../features/invoices/InvoiceArchive";
import InvoiceStats from "../features/invoices/InvoiceStats";
import { getInvoiceStats } from "../features/invoices/invoiceStats";
import { downloadDocument } from "../features/documents/downloadDocument";
import {
  getListIdFromSearchParams,
  matchesDocumentSearch,
} from "../features/documents/documentUtils";
import { invalidateListAndDocumentQueries, queryKeys } from "../queryKeys";
import type { Contract } from "../types";

const Invoices: React.FC = () => {
  const queryClient = useQueryClient();
  const [searchParams] = useSearchParams();
  const listId = getListIdFromSearchParams(searchParams);
  const [isUploadOpen, setIsUploadOpen] = useState(false);
  const [editingInvoice, setEditingInvoice] = useState<Contract | null>(null);
  const [search, setSearch] = useState("");

  const { data: invoices = [], isLoading } = useQuery<Contract[]>(
    queryKeys.invoicesForList(listId),
    () =>
      fetchAllContracts({
        document_type: "invoice",
        sort_by: "uploaded_at",
        sort_order: "desc",
        ...(listId ? { list_id: listId } : {}),
      }),
  );

  const filteredInvoices = useMemo(
    () => invoices.filter((invoice) => matchesDocumentSearch(invoice, search)),
    [invoices, search],
  );
  const stats = getInvoiceStats(invoices);

  const openUpload = (invoice: Contract | null = null) => {
    setEditingInvoice(invoice);
    setIsUploadOpen(true);
  };

  const handleDelete = async (invoice: Contract) => {
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
      await api.delete(`/contracts/${invoice.id}`);
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

  return (
    <div className="app-page">
      <PageHeader
        eyebrow="Invoice Desk"
        title="Rechnungen"
        description="Ein schneller, eigenständiger Ablageprozess für Rechnungen – auch wenn kein Vertrag existiert."
        actions={
          <button onClick={() => openUpload()} className="btn-primary">
            <FiPlus /> Rechnung hochladen
          </button>
        }
      />

      <InvoiceStats invoiceCount={invoices.length} stats={stats} />
      <InvoiceArchive
        invoices={filteredInvoices}
        onCreate={() => openUpload()}
        onDelete={handleDelete}
        onDownload={handleDownload}
        onEdit={openUpload}
        onSearchChange={setSearch}
        searchQuery={search}
      />

      <UploadModal
        isOpen={isUploadOpen}
        onClose={() => {
          setIsUploadOpen(false);
          setEditingInvoice(null);
        }}
        initialData={editingInvoice}
        documentType="invoice"
      />
    </div>
  );
};

export default Invoices;
