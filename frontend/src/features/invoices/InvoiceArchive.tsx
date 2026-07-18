import React from "react";
import { FiFileText, FiPlus, FiSearch } from "react-icons/fi";
import { EmptyState } from "../../components/ui";
import type { Contract } from "../../types";
import InvoiceRow from "./InvoiceRow";

interface InvoiceArchiveProps {
  invoices: Contract[];
  onCreate: () => void;
  onDelete: (invoice: Contract) => void | Promise<void>;
  onDownload: (invoice: Contract) => void | Promise<void>;
  onEdit: (invoice: Contract) => void;
  onSearchChange: (searchQuery: string) => void;
  searchQuery: string;
}

const InvoiceArchive: React.FC<InvoiceArchiveProps> = ({
  invoices,
  onCreate,
  onDelete,
  onDownload,
  onEdit,
  onSearchChange,
  searchQuery,
}) => (
  <section className="surface overflow-hidden">
    <div className="flex flex-col gap-4 p-5 sm:flex-row sm:items-center sm:justify-between sm:px-6">
      <div>
        <p className="eyebrow">Rechnungsarchiv</p>
        <h2 className="section-title mt-1">Alle Belege</h2>
      </div>
      <label className="relative block sm:w-72">
        <FiSearch className="absolute left-3.5 top-1/2 -translate-y-1/2 text-[#657080]" />
        <input
          value={searchQuery}
          onChange={(event) => onSearchChange(event.target.value)}
          className="field py-2.5 pl-10"
          placeholder="Lieferant oder Tag…"
        />
      </label>
    </div>
    {invoices.length ? (
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
        {invoices.map((invoice) => (
          <InvoiceRow
            key={invoice.id}
            invoice={invoice}
            onDelete={onDelete}
            onDownload={onDownload}
            onEdit={onEdit}
          />
        ))}
      </>
    ) : (
      <div className="p-5">
        <EmptyState
          icon={FiFileText}
          title={
            searchQuery ? "Keine passenden Rechnungen" : "Noch keine Rechnungen"
          }
          description={
            searchQuery
              ? "Versuche einen anderen Suchbegriff."
              : "Lade eine Rechnung direkt hoch – ein zugehöriger Vertrag ist nicht nötig."
          }
          action={
            !searchQuery ? (
              <button onClick={onCreate} className="btn-primary">
                <FiPlus /> Erste Rechnung hochladen
              </button>
            ) : undefined
          }
        />
      </div>
    )}
  </section>
);

export default InvoiceArchive;
