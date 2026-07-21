import type { FC } from "react";
import {
  FiCheck,
  FiDownload,
  FiEdit3,
  FiFileText,
  FiFolder,
  FiMoreHorizontal,
  FiTrash2,
} from "react-icons/fi";
import type { Contract } from "../../types";
import { formatContractDate } from "../../utils/contractPresentation";
import { formatGermanNumber } from "../../utils/formatUtils";

interface InvoiceCardProps {
  invoice: Contract;
  isAdmin: boolean;
  isMenuOpen: boolean;
  isSelected: boolean;
  isSelectionMode: boolean;
  onAssignToList: (invoice: Contract) => void;
  onDelete: (invoice: Contract) => void | Promise<void>;
  onDownload: (invoice: Contract) => void | Promise<void>;
  onEdit: (invoice: Contract) => void;
  onToggleMenu: () => void;
  onToggleSelection: (invoice: Contract) => void;
}

const InvoiceCard: FC<InvoiceCardProps> = ({
  invoice,
  isAdmin,
  isMenuOpen,
  isSelected,
  isSelectionMode,
  onAssignToList,
  onDelete,
  onDownload,
  onEdit,
  onToggleMenu,
  onToggleSelection,
}) => {
  const workspaceNames = invoice.lists
    ?.map((workspace) =>
      workspace.is_default
        ? `Persönlicher Workspace${
            workspace.owner_username ? ` · ${workspace.owner_username}` : ""
          }`
        : workspace.name,
    )
    .join(", ");
  const invoiceDate = invoice.start_date || invoice.uploaded_at;
  const hasMenuActions =
    isAdmin || invoice.can_write || invoice.can_delete;

  return (
    <article
      className={[
        "surface surface-interactive relative overflow-visible p-5 sm:p-6",
        isSelected ? "ring-2 ring-[#b8f15a]/70" : "",
      ].join(" ")}
    >
      <div className="mb-5 flex items-start gap-4">
        {isSelectionMode && (
          <button
            type="button"
            aria-label={`${invoice.title} ${
              isSelected ? "abwählen" : "auswählen"
            }`}
            aria-pressed={isSelected}
            onClick={() => onToggleSelection(invoice)}
            className={[
              "mt-2 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border",
              "transition focus:outline-none focus-visible:ring-2 focus-visible:ring-[#b8f15a]",
              isSelected
                ? "border-[#b8f15a] bg-[#b8f15a] text-[#111700]"
                : "border-white/[0.18] bg-white/[0.04] text-transparent hover:border-[#b8f15a]/70",
            ].join(" ")}
          >
            <FiCheck size={16} />
          </button>
        )}
        <span
          className={[
            "flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl border",
            "border-[#b8f15a]/15 bg-[#b8f15a]/10 text-[#b8f15a]",
          ].join(" ")}
        >
          <FiFileText size={21} />
        </span>
        <div className="min-w-0 flex-1">
          <div className="mb-1.5 flex flex-wrap items-center gap-2">
            <span className="chip border border-[#b8f15a]/15 bg-[#b8f15a]/10 text-[#b8f15a]">
              Rechnung
            </span>
            {invoice.is_protected && (
              <span className="chip border-[#b28cff]/15 bg-[#b28cff]/10 text-[#c9adff]">
                Geschützt
              </span>
            )}
          </div>
          <h2 className="truncate text-lg font-semibold tracking-[-.02em] text-white">
            {invoice.title}
          </h2>
          <p className="mt-1 line-clamp-2 text-sm leading-5 muted">
            {invoice.description || "Keine Beschreibung hinterlegt."}
          </p>
        </div>
        {!isSelectionMode && hasMenuActions && (
          <div className="relative">
            <button
              onClick={onToggleMenu}
              className="icon-btn"
              aria-label="Weitere Aktionen"
            >
              <FiMoreHorizontal />
            </button>
            {isMenuOpen && (
              <div className="surface-raised absolute right-0 top-11 z-20 w-56 p-1.5">
                <button
                  onClick={() => onEdit(invoice)}
                  disabled={!invoice.can_write}
                  className="btn-ghost w-full justify-start disabled:hidden"
                >
                  <FiEdit3 /> Bearbeiten
                </button>
                {isAdmin && (
                  <button
                    onClick={() => onAssignToList(invoice)}
                    className="btn-ghost w-full justify-start"
                  >
                    <FiFolder /> Workspaces verwalten
                  </button>
                )}
                {invoice.can_delete && (
                  <button
                    onClick={() => onDelete(invoice)}
                    disabled={invoice.is_protected}
                    className="btn-ghost w-full justify-start text-red-300 hover:text-red-200 disabled:hidden"
                  >
                    <FiTrash2 /> Löschen
                  </button>
                )}
              </div>
            )}
          </div>
        )}
      </div>

      <div
        className={[
          "grid grid-cols-2 gap-px overflow-hidden rounded-2xl border",
          "border-white/[0.07] bg-white/[0.07] sm:grid-cols-4",
        ].join(" ")}
      >
        {[
          [
            "Rechnungsdatum",
            formatContractDate(invoiceDate, invoice.business_timezone),
          ],
          [
            "Betrag",
            invoice.value != null
              ? `${formatGermanNumber(invoice.value)} €`
              : "–",
          ],
          ["Workspace", workspaceNames || "Nicht zugeordnet"],
          ["Status", invoice.is_protected ? "Geschützt" : "Erfasst"],
        ].map(([label, value]) => (
          <div key={label} className="min-w-0 bg-[#0d1117] px-3 py-3">
            <p className="text-[10px] font-bold uppercase tracking-[.12em] text-[#596474]">
              {label}
            </p>
            <p
              className="mt-1 truncate text-xs font-semibold text-[#d8dee7]"
              title={value}
            >
              {value}
            </p>
          </div>
        ))}
      </div>

      <div className="mt-5 flex flex-col gap-3 border-t border-white/[0.06] pt-4 sm:flex-row sm:items-center">
        <div className="flex min-w-0 flex-1 flex-wrap gap-1.5">
          {invoice.tags.length ? (
            invoice.tags.slice(0, 4).map((tag) => (
              <span key={tag.name} className="chip">
                #{tag.name}
              </span>
            ))
          ) : (
            <span className="text-xs muted">Keine Tags</span>
          )}
        </div>
        <button
          onClick={() => onDownload(invoice)}
          className="btn-secondary min-h-10 px-3"
        >
          <FiDownload /> Download
        </button>
      </div>
    </article>
  );
};

export default InvoiceCard;
