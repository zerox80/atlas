import type { FC } from "react";
import { FiFileText, FiPlus, FiSearch } from "react-icons/fi";
import { EmptyState } from "../../components/ui";
import type { Contract } from "../../types";
import InvoiceCard from "./InvoiceCard";

interface InvoiceArchiveProps {
  invoices: Contract[];
  isAdmin: boolean;
  isSelectionMode: boolean;
  onAssignToList: (invoice: Contract) => void;
  onCreate?: () => void;
  onDelete: (invoice: Contract) => void | Promise<void>;
  onDownload: (invoice: Contract) => void | Promise<void>;
  onEdit: (invoice: Contract) => void;
  onSearchChange: (searchQuery: string) => void;
  onToggleMenu: (invoiceId: number) => void;
  onToggleSelection: (invoice: Contract) => void;
  openMenuId: number | null;
  searchQuery: string;
  selectedInvoiceIds: Set<number>;
}

const InvoiceArchive: FC<InvoiceArchiveProps> = ({
  invoices,
  isAdmin,
  isSelectionMode,
  onAssignToList,
  onCreate,
  onDelete,
  onDownload,
  onEdit,
  onSearchChange,
  onToggleMenu,
  onToggleSelection,
  openMenuId,
  searchQuery,
  selectedInvoiceIds,
}) => (
  <section>
    <div className="surface mb-5 flex flex-col gap-4 p-5 sm:flex-row sm:items-center sm:justify-between sm:px-6">
      <div>
        <p className="eyebrow">Rechnungsarchiv</p>
        <h2 className="section-title mt-1">Alle Belege</h2>
      </div>
      <label className="relative block sm:w-72">
        <FiSearch className="absolute left-3.5 top-1/2 -translate-y-1/2 text-[#657080]" />
        <input
          value={searchQuery}
          maxLength={200}
          onChange={(event) => onSearchChange(event.target.value)}
          className="field py-2.5 pl-10"
          placeholder="Lieferant oder Tag …"
        />
      </label>
    </div>

    {invoices.length ? (
      <div className="grid gap-4 xl:grid-cols-2">
        {invoices.map((invoice) => (
          <InvoiceCard
            key={invoice.id}
            invoice={invoice}
            isAdmin={isAdmin}
            isMenuOpen={openMenuId === invoice.id}
            isSelected={selectedInvoiceIds.has(invoice.id)}
            isSelectionMode={isSelectionMode}
            onAssignToList={onAssignToList}
            onDelete={onDelete}
            onDownload={onDownload}
            onEdit={onEdit}
            onToggleMenu={() => onToggleMenu(invoice.id)}
            onToggleSelection={onToggleSelection}
          />
        ))}
      </div>
    ) : (
      <div className="surface p-5">
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
            !searchQuery && onCreate ? (
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
