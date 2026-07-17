import React, { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import {
  FiDownload,
  FiEdit3,
  FiFileText,
  FiPlus,
  FiSearch,
  FiTrash2,
  FiTrendingUp,
} from "react-icons/fi";
import api, { fetchAllContracts } from "../api";
import UploadModal from "../components/UploadModal";
import { EmptyState, LoadingState, PageHeader } from "../components/ui";
import { formatGermanNumber } from "../utils/formatUtils";
import { triggerBlobDownload } from "../utils/downloadUtils";
import type { Contract } from "../types";

const Invoices: React.FC = () => {
  const queryClient = useQueryClient();
  const [searchParams] = useSearchParams();
  const listIdParam = searchParams.get("list_id");
  const listId =
    listIdParam && /^\d+$/.test(listIdParam) ? Number(listIdParam) : null;
  const [isUploadOpen, setIsUploadOpen] = useState(false);
  const [editingInvoice, setEditingInvoice] = useState<Contract | null>(null);
  const [search, setSearch] = useState("");

  const { data: invoices = [], isLoading } = useQuery<Contract[]>(
    ["invoices", listId],
    async () => {
      return fetchAllContracts({
          document_type: "invoice",
          sort_by: "uploaded_at",
          sort_order: "desc",
          ...(listId ? { list_id: listId } : {}),
      });
    },
  );

  const filtered = useMemo(
    () =>
      invoices.filter((invoice) =>
        `${invoice.title} ${invoice.description || ""} ${invoice.tags.map((tag) => tag.name).join(" ")}`
          .toLowerCase()
          .includes(search.toLowerCase()),
      ),
    [invoices, search],
  );
  const total = invoices.reduce(
    (sum, invoice) => sum + (invoice.value || 0),
    0,
  );
  const currentMonthTotal = invoices
    .filter((invoice) => {
      const value = new Date(invoice.start_date || invoice.uploaded_at);
      const now = new Date();
      return (
        value.getMonth() === now.getMonth() &&
        value.getFullYear() === now.getFullYear()
      );
    })
    .reduce((sum, invoice) => sum + (invoice.value || 0), 0);

  const handleDelete = async (invoice: Contract) => {
    if (invoice.is_protected)
      return alert(
        "Diese Rechnung ist geschützt. Bitte heben Sie zuerst den Schutz auf.",
      );
    if (
      !window.confirm(
        `Möchten Sie die Rechnung „${invoice.title}“ wirklich löschen?`,
      )
    )
      return;
    try {
      await api.delete(`/contracts/${invoice.id}`);
      await Promise.all([
        queryClient.invalidateQueries(["invoices"]),
        queryClient.invalidateQueries(["contracts"]),
        queryClient.invalidateQueries(["workspace-documents"]),
      ]);
    } catch {
      alert("Die Rechnung konnte nicht gelöscht werden.");
    }
  };

  const handleDownload = async (invoice: Contract) => {
    try {
      const response = await api.get<Blob>(
        `/contracts/${invoice.id}/download`,
        { responseType: "blob" },
      );
      const extension = invoice.file_extension?.startsWith(".")
        ? invoice.file_extension
        : `.${invoice.file_extension || "pdf"}`;
      triggerBlobDownload(
        response.data,
        invoice.title.endsWith(extension)
          ? invoice.title
          : `${invoice.title}${extension}`,
      );
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
          <button onClick={() => setIsUploadOpen(true)} className="btn-primary">
            <FiPlus /> Rechnung hochladen
          </button>
        }
      />

      <section className="mb-5 grid gap-4 sm:grid-cols-3">
        <article className="surface p-5">
          <p className="eyebrow">Gesamtes Archiv</p>
          <p className="metric-value mt-3">{formatGermanNumber(total)} €</p>
          <p className="mt-2 text-xs muted">aus {invoices.length} Rechnungen</p>
        </article>
        <article className="surface p-5">
          <p className="eyebrow">Dieser Monat</p>
          <p className="metric-value mt-3 text-[#b8f15a]">
            {formatGermanNumber(currentMonthTotal)} €
          </p>
          <p className="mt-2 text-xs muted">nach Rechnungsdatum</p>
        </article>
        <article className="surface p-5">
          <p className="eyebrow">Ø Rechnungswert</p>
          <p className="metric-value mt-3">
            {formatGermanNumber(invoices.length ? total / invoices.length : 0)}{" "}
            €
          </p>
          <p className="mt-2 flex items-center gap-1.5 text-xs muted">
            <FiTrendingUp className="text-[#77a7ff]" /> automatisch berechnet
          </p>
        </article>
      </section>

      <section className="surface overflow-hidden">
        <div className="flex flex-col gap-4 p-5 sm:flex-row sm:items-center sm:justify-between sm:px-6">
          <div>
            <p className="eyebrow">Rechnungsarchiv</p>
            <h2 className="section-title mt-1">Alle Belege</h2>
          </div>
          <label className="relative block sm:w-72">
            <FiSearch className="absolute left-3.5 top-1/2 -translate-y-1/2 text-[#657080]" />
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              className="field py-2.5 pl-10"
              placeholder="Lieferant oder Tag…"
            />
          </label>
        </div>
        {filtered.length ? (
          <>
            <div
              className={[
                "hidden",
                "grid-cols-[minmax(240px,1.5fr)_140px_140px_minmax(120px,.7fr)_128px]",
                "gap-4 border-y border-white/[0.06] bg-white/[0.02] px-6 py-2.5",
                "text-[10px] font-bold uppercase tracking-[.14em] text-[#5e6878] xl:grid",
              ].join(" ")}
            >
              <span>Rechnung</span>
              <span>Datum</span>
              <span>Status</span>
              <span className="text-right">Betrag</span>
              <span />
            </div>
            {filtered.map((invoice) => (
              <article
                key={invoice.id}
                className={[
                  "data-row grid-cols-[minmax(0,1fr)_auto]",
                  "xl:grid-cols-[minmax(240px,1.5fr)_140px_140px_minmax(120px,.7fr)_128px]",
                  "xl:gap-4",
                ].join(" ")}
              >
                <div className="flex min-w-0 items-center gap-3">
                  <span
                    className={[
                      "flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border",
                      "border-[#b8f15a]/15 bg-[#b8f15a]/10 text-[#b8f15a]",
                    ].join(" ")}
                  >
                    <FiFileText />
                  </span>
                  <span className="min-w-0">
                    <strong className="block truncate text-sm font-semibold text-white">
                      {invoice.title}
                    </strong>
                    <span className="mt-1 flex gap-1.5 overflow-hidden">
                      {invoice.tags.slice(0, 2).map((tag) => (
                        <small
                          key={tag.name}
                          className="truncate text-[11px] muted"
                        >
                          #{tag.name}
                        </small>
                      ))}
                    </span>
                  </span>
                </div>
                <div
                  className={[
                    "col-span-2 grid grid-cols-1 gap-2 border-t border-white/[0.06] pt-3",
                    "sm:grid-cols-3 xl:col-span-1 xl:contents xl:border-0 xl:pt-0",
                  ].join(" ")}
                >
                  <p className="flex items-center justify-between gap-2 text-sm muted xl:block">
                    <span className="text-[10px] font-bold uppercase tracking-wider text-[#5e6878] xl:hidden">
                      Datum
                    </span>
                    {invoice.start_date
                      ? new Date(invoice.start_date).toLocaleDateString("de-DE")
                      : "–"}
                  </p>
                  <div className="flex items-center justify-between gap-2 xl:block">
                    <span className="text-[10px] font-bold uppercase tracking-wider text-[#5e6878] xl:hidden">
                      Status
                    </span>
                    <span
                      className={[
                        "chip w-fit",
                        invoice.is_protected
                          ? "border-[#b28cff]/15 bg-[#b28cff]/10 text-[#c9adff]"
                          : "border-[#b8f15a]/15 bg-[#b8f15a]/10 text-[#b8f15a]",
                      ].join(" ")}
                    >
                      {invoice.is_protected ? "Geschützt" : "Erfasst"}
                    </span>
                  </div>
                  <div className="flex items-center justify-between gap-2 xl:block">
                    <span className="text-[10px] font-bold uppercase tracking-wider text-[#5e6878] xl:hidden">
                      Betrag
                    </span>
                    <p className="text-base font-bold text-white xl:text-right">
                      {invoice.value != null
                        ? `${formatGermanNumber(invoice.value)} €`
                        : "–"}
                    </p>
                  </div>
                </div>
                <div
                  className={[
                    "col-start-2 row-start-1 flex shrink-0 justify-end gap-1 self-center",
                    "xl:col-auto xl:row-auto",
                  ].join(" ")}
                >
                  <button
                    onClick={() => handleDownload(invoice)}
                    className="icon-btn"
                    title="Herunterladen"
                  >
                    <FiDownload />
                  </button>
                  {invoice.can_write && (
                    <button
                      onClick={() => {
                        setEditingInvoice(invoice);
                        setIsUploadOpen(true);
                      }}
                      className="icon-btn"
                      title="Bearbeiten"
                    >
                      <FiEdit3 />
                    </button>
                  )}
                  {invoice.can_delete && (
                    <button
                      onClick={() => handleDelete(invoice)}
                      disabled={invoice.is_protected}
                      className="icon-btn hover:text-red-300 disabled:cursor-not-allowed disabled:opacity-30"
                      title="Löschen"
                    >
                      <FiTrash2 />
                    </button>
                  )}
                </div>
              </article>
            ))}
          </>
        ) : (
          <div className="p-5">
            <EmptyState
              icon={FiFileText}
              title={
                search ? "Keine passenden Rechnungen" : "Noch keine Rechnungen"
              }
              description={
                search
                  ? "Versuche einen anderen Suchbegriff."
                  : "Lade eine Rechnung direkt hoch – ein zugehöriger Vertrag ist nicht nötig."
              }
              action={
                !search ? (
                  <button
                    onClick={() => setIsUploadOpen(true)}
                    className="btn-primary"
                  >
                    <FiPlus /> Erste Rechnung hochladen
                  </button>
                ) : undefined
              }
            />
          </div>
        )}
      </section>

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
