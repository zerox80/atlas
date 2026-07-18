import React from "react";
import { FiDownload, FiEdit3, FiFileText, FiTrash2 } from "react-icons/fi";
import type { Contract } from "../../types";
import { formatGermanNumber } from "../../utils/formatUtils";
import { formatContractDate } from "../../utils/contractPresentation";

interface InvoiceRowProps {
  invoice: Contract;
  onDelete: (invoice: Contract) => void | Promise<void>;
  onDownload: (invoice: Contract) => void | Promise<void>;
  onEdit: (invoice: Contract) => void;
}

const InvoiceRow: React.FC<InvoiceRowProps> = ({
  invoice,
  onDelete,
  onDownload,
  onEdit,
}) => (
  <article
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
            <small key={tag.name} className="truncate text-[11px] muted">
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
          ? formatContractDate(invoice.start_date, invoice.business_timezone)
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
        onClick={() => onDownload(invoice)}
        className="icon-btn"
        title="Herunterladen"
      >
        <FiDownload />
      </button>
      {invoice.can_write && (
        <button
          onClick={() => onEdit(invoice)}
          className="icon-btn"
          title="Bearbeiten"
        >
          <FiEdit3 />
        </button>
      )}
      {invoice.can_delete && (
        <button
          onClick={() => onDelete(invoice)}
          disabled={invoice.is_protected}
          className="icon-btn hover:text-red-300 disabled:cursor-not-allowed disabled:opacity-30"
          title="Löschen"
        >
          <FiTrash2 />
        </button>
      )}
    </div>
  </article>
);

export default InvoiceRow;
