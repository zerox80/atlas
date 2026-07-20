import React from "react";
import {
  FiActivity,
  FiCheck,
  FiDownload,
  FiFileText,
  FiFolder,
  FiMessageCircle,
  FiMoreHorizontal,
  FiShield,
  FiTrash2,
} from "react-icons/fi";
import type { Contract } from "../../types";
import {
  formatContractDate,
  getContractState,
} from "../../utils/contractPresentation";
import { formatGermanNumber } from "../../utils/formatUtils";

interface ContractCardProps {
  contract: Contract;
  isAdmin: boolean;
  isMenuOpen: boolean;
  isSelected: boolean;
  isSelectionMode: boolean;
  onAssignToList: (contract: Contract) => void;
  onDelete: (contract: Contract) => void | Promise<void>;
  onDownload: (contract: Contract) => void | Promise<void>;
  onEdit: (contract: Contract) => void;
  onOpenAudit: (contract: Contract) => void;
  onOpenChat: (contract: Contract) => void;
  onOpenDetails: (contract: Contract) => void;
  onToggleMenu: () => void;
  onToggleProtection: (contract: Contract) => void | Promise<void>;
  onToggleSelection: (contract: Contract) => void;
}

const ContractCard: React.FC<ContractCardProps> = ({
  contract,
  isAdmin,
  isMenuOpen,
  isSelected,
  isSelectionMode,
  onAssignToList,
  onDelete,
  onDownload,
  onEdit,
  onOpenAudit,
  onOpenChat,
  onOpenDetails,
  onToggleMenu,
  onToggleProtection,
  onToggleSelection,
}) => {
  const status = getContractState(contract);
  const StatusIcon = status.icon;

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
            aria-label={`${contract.title} ${
              isSelected ? "abwählen" : "auswählen"
            }`}
            aria-pressed={isSelected}
            onClick={() => onToggleSelection(contract)}
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
            "border-[#77a7ff]/15 bg-[#77a7ff]/10 text-[#77a7ff]",
          ].join(" ")}
        >
          <FiFileText size={21} />
        </span>
        <div className="min-w-0 flex-1">
          <div className="mb-1.5 flex flex-wrap items-center gap-2">
            <span className={`chip border ${status.tone}`}>
              <StatusIcon />
              {status.label}
            </span>
            {contract.is_protected && (
              <span className="chip border-[#b28cff]/15 bg-[#b28cff]/10 text-[#c9adff]">
                Geschützt
              </span>
            )}
          </div>
          <h2 className="truncate text-lg font-semibold tracking-[-.02em]">
            <button
              onClick={() => onOpenDetails(contract)}
              className={[
                "max-w-full truncate text-left text-white transition-colors",
                "hover:text-[#b8f15a] hover:underline focus:outline-none",
                "focus-visible:rounded focus-visible:ring-2 focus-visible:ring-[#b8f15a]",
              ].join(" ")}
            >
              {contract.title}
            </button>
          </h2>
          <p className="mt-1 line-clamp-2 text-sm leading-5 muted">
            {contract.description || "Keine Beschreibung hinterlegt."}
          </p>
        </div>
        {!isSelectionMode && (
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
                  onClick={() => onEdit(contract)}
                  disabled={!contract.can_write}
                  className="btn-ghost w-full justify-start disabled:hidden"
                >
                  Bearbeiten
                </button>
                {isAdmin && (
                  <button
                    onClick={() => onAssignToList(contract)}
                    className="btn-ghost w-full justify-start"
                  >
                    <FiFolder /> Workspaces verwalten
                  </button>
                )}
                <button
                  onClick={() => onOpenAudit(contract)}
                  className="btn-ghost w-full justify-start"
                >
                  <FiActivity /> Aktivitäten
                </button>
                {contract.can_manage_protection && (
                  <button
                    onClick={() => onToggleProtection(contract)}
                    className="btn-ghost w-full justify-start"
                  >
                    <FiShield /> Schutz{" "}
                    {contract.is_protected ? "aufheben" : "aktivieren"}
                  </button>
                )}
                {contract.can_delete && (
                  <button
                    onClick={() => onDelete(contract)}
                    className="btn-ghost w-full justify-start text-red-300 hover:text-red-200"
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
          ["Beginn", formatContractDate(contract.start_date, contract.business_timezone)],
          ["Ende", formatContractDate(contract.end_date, contract.business_timezone)],
          ["Kündigungsfenster", status.deadline],
          [
            "Vertragswert",
            contract.value != null
              ? `${formatGermanNumber(contract.value)} €`
              : "–",
          ],
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
          {contract.tags.length ? (
            contract.tags.slice(0, 4).map((tag) => (
              <span key={tag.name} className="chip">
                #{tag.name}
              </span>
            ))
          ) : (
            <span className="text-xs muted">Keine Tags</span>
          )}
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => onDownload(contract)}
            className="btn-secondary min-h-10 px-3"
          >
            <FiDownload />
            <span className="hidden sm:inline">Download</span>
          </button>
          {contract.file_extension?.toLowerCase().replace(/^\./, "") ===
            "pdf" && (
            <button
              onClick={() => onOpenChat(contract)}
              className="btn-secondary min-h-10 px-3 text-[#c9adff]"
            >
              <FiMessageCircle /> KI-Chat
            </button>
          )}
        </div>
      </div>
    </article>
  );
};

export default ContractCard;
