import React, { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import {
  FiActivity,
  FiDownload,
  FiFileText,
  FiFolder,
  FiMessageCircle,
  FiMoreHorizontal,
  FiPlus,
  FiSearch,
  FiShield,
  FiTrash2,
} from "react-icons/fi";
import api, { toggleContractProtection } from "../api";
import UploadModal from "../components/UploadModal";
import ContractChat from "../components/ContractChat";
import AddToListModal from "../components/AddToListModal";
import AuditModal from "../components/AuditModal";
import ContractDetailsModal from "../components/ContractDetailsModal";
import { EmptyState, LoadingState, PageHeader } from "../components/ui";
import type { Contract } from "../types";
import {
  formatContractDate,
  getContractState,
  type ContractStateKey,
} from "../utils/contractPresentation";
import { triggerBlobDownload } from "../utils/downloadUtils";
import { formatGermanNumber } from "../utils/formatUtils";

type ViewFilter = "all" | ContractStateKey;

const Contracts: React.FC = () => {
  const queryClient = useQueryClient();
  const [searchParams] = useSearchParams();
  const listIdParam = searchParams.get("list_id");
  const listId =
    listIdParam && /^\d+$/.test(listIdParam) ? Number(listIdParam) : null;
  const [isUploadOpen, setIsUploadOpen] = useState(false);
  const [editingContract, setEditingContract] = useState<Contract | null>(null);
  const [chatContract, setChatContract] = useState<Contract | null>(null);
  const [listContract, setListContract] = useState<Contract | null>(null);
  const [auditContract, setAuditContract] = useState<Contract | null>(null);
  const [detailsContract, setDetailsContract] = useState<Contract | null>(null);
  const [filter, setFilter] = useState<ViewFilter>("all");
  const [search, setSearch] = useState("");
  const [openMenu, setOpenMenu] = useState<number | null>(null);

  const { data = [], isLoading } = useQuery<Contract[]>(
    ["contracts", listId],
    async () => {
      const response = await api.get<Contract[]>("/contracts", {
        params: {
          document_type: "contract",
          sort_by: "uploaded_at",
          sort_order: "desc",
          ...(listId ? { list_id: listId } : {}),
        },
      });
      return response.data;
    },
  );

  const filtered = useMemo(
    () =>
      data.filter((contract) => {
        const matchesQuery =
          `${contract.title} ${contract.description || ""} ${contract.tags.map((tag) => tag.name).join(" ")}`
            .toLowerCase()
            .includes(search.toLowerCase());
        return (
          matchesQuery &&
          (filter === "all" || getContractState(contract).key === filter)
        );
      }),
    [data, filter, search],
  );

  const counts = useMemo(
    () => ({
      all: data.length,
      attention: data.filter(
        (item) => getContractState(item).key === "attention",
      ).length,
      active: data.filter((item) => getContractState(item).key === "active")
        .length,
      expired: data.filter((item) => getContractState(item).key === "expired")
        .length,
    }),
    [data],
  );

  const handleDelete = async (contract: Contract) => {
    setOpenMenu(null);
    if (contract.is_protected)
      return alert(
        "Dieser Vertrag ist geschützt. Bitte heben Sie zuerst den Schutz auf.",
      );
    if (
      !window.confirm(
        `Möchten Sie den Vertrag „${contract.title}“ wirklich löschen?`,
      )
    )
      return;
    try {
      await api.delete(`/contracts/${contract.id}`);
      await Promise.all([
        queryClient.invalidateQueries(["contracts"]),
        queryClient.invalidateQueries(["workspace-documents"]),
      ]);
    } catch {
      alert("Der Vertrag konnte nicht gelöscht werden.");
    }
  };

  const handleDownload = async (contract: Contract) => {
    try {
      const response = await api.get<Blob>(
        `/contracts/${contract.id}/download`,
        {
          responseType: "blob",
        },
      );
      const extension = contract.file_extension?.startsWith(".")
        ? contract.file_extension
        : `.${contract.file_extension || "pdf"}`;
      triggerBlobDownload(
        response.data,
        contract.title.endsWith(extension)
          ? contract.title
          : `${contract.title}${extension}`,
      );
    } catch {
      alert("Das Dokument konnte nicht heruntergeladen werden.");
    }
  };

  const handleProtection = async (contract: Contract) => {
    setOpenMenu(null);
    try {
      await toggleContractProtection(contract.id);
      await Promise.all([
        queryClient.invalidateQueries(["contracts"]),
        queryClient.invalidateQueries(["workspace-documents"]),
      ]);
    } catch {
      alert("Der Schutzstatus konnte nicht geändert werden.");
    }
  };

  if (isLoading) return <LoadingState label="Verträge werden geladen" />;

  return (
    <div className="app-page">
      <PageHeader
        eyebrow="Contract Operations"
        title="Verträge & Fristen"
        description="Eine fokussierte Arbeitsansicht für Laufzeiten, Kündigungsfenster und Vertragswerte."
        actions={
          <button onClick={() => setIsUploadOpen(true)} className="btn-primary">
            <FiPlus /> Vertrag hinzufügen
          </button>
        }
      />

      <div className="surface mb-5 flex flex-col gap-3 p-3 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex gap-1 overflow-x-auto">
          {(
            [
              ["all", "Alle"],
              ["attention", "Handlungsbedarf"],
              ["active", "Aktiv"],
              ["expired", "Archiv"],
            ] as [ViewFilter, string][]
          ).map(([key, label]) => (
            <button
              key={key}
              onClick={() => setFilter(key)}
              className={[
                "flex shrink-0 items-center gap-2 rounded-xl px-3.5 py-2.5",
                "text-sm font-semibold transition",
                filter === key
                  ? "bg-white/[0.09] text-white"
                  : "text-[#7f8999] hover:text-white",
              ].join(" ")}
            >
              {label}
              <span
                className={[
                  "rounded-full px-1.5 py-0.5 text-[10px]",
                  filter === key
                    ? "bg-[#b8f15a] text-[#111700]"
                    : "bg-white/[0.06]",
                ].join(" ")}
              >
                {counts[key]}
              </span>
            </button>
          ))}
        </div>
        <label className="relative block min-w-0 lg:w-72">
          <FiSearch className="absolute left-3.5 top-1/2 -translate-y-1/2 text-[#667181]" />
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Verträge durchsuchen…"
            className="field py-2.5 pl-10"
          />
        </label>
      </div>

      {filtered.length ? (
        <div className="grid gap-4 xl:grid-cols-2">
          {filtered.map((contract) => {
            const status = getContractState(contract);
            const StatusIcon = status.icon;
            return (
              <article
                key={contract.id}
                className="surface surface-interactive relative overflow-visible p-5 sm:p-6"
              >
                <div className="mb-5 flex items-start gap-4">
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
                        onClick={() => setDetailsContract(contract)}
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
                  <div className="relative">
                    <button
                      onClick={() =>
                        setOpenMenu(
                          openMenu === contract.id ? null : contract.id,
                        )
                      }
                      className="icon-btn"
                      aria-label="Weitere Aktionen"
                    >
                      <FiMoreHorizontal />
                    </button>
                    {openMenu === contract.id && (
                      <div className="surface-raised absolute right-0 top-11 z-20 w-56 p-1.5">
                        <button
                          onClick={() => {
                            setEditingContract(contract);
                            setIsUploadOpen(true);
                            setOpenMenu(null);
                          }}
                          disabled={!contract.can_write}
                          className="btn-ghost w-full justify-start disabled:hidden"
                        >
                          Bearbeiten
                        </button>
                        <button
                          onClick={() => {
                            setListContract(contract);
                            setOpenMenu(null);
                          }}
                          className="btn-ghost w-full justify-start"
                        >
                          <FiFolder /> Sammlung zuweisen
                        </button>
                        <button
                          onClick={() => {
                            setAuditContract(contract);
                            setOpenMenu(null);
                          }}
                          className="btn-ghost w-full justify-start"
                        >
                          <FiActivity /> Aktivitäten
                        </button>
                        {contract.can_manage_protection && (
                          <button
                            onClick={() => handleProtection(contract)}
                            className="btn-ghost w-full justify-start"
                          >
                            <FiShield /> Schutz{" "}
                            {contract.is_protected ? "aufheben" : "aktivieren"}
                          </button>
                        )}
                        {contract.can_delete && (
                          <button
                            onClick={() => handleDelete(contract)}
                            className="btn-ghost w-full justify-start text-red-300 hover:text-red-200"
                          >
                            <FiTrash2 /> Löschen
                          </button>
                        )}
                      </div>
                    )}
                  </div>
                </div>

                <div
                  className={[
                    "grid grid-cols-2 gap-px overflow-hidden rounded-2xl border",
                    "border-white/[0.07] bg-white/[0.07] sm:grid-cols-4",
                  ].join(" ")}
                >
                  {[
                    ["Beginn", formatContractDate(contract.start_date)],
                    ["Ende", formatContractDate(contract.end_date)],
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
                      onClick={() => handleDownload(contract)}
                      className="btn-secondary min-h-10 px-3"
                    >
                      <FiDownload />
                      <span className="hidden sm:inline">Download</span>
                    </button>
                    {contract.file_extension
                      ?.toLowerCase()
                      .replace(/^\./, "") === "pdf" && (
                      <button
                        onClick={() => setChatContract(contract)}
                        className="btn-secondary min-h-10 px-3 text-[#c9adff]"
                      >
                        <FiMessageCircle /> KI-Chat
                      </button>
                    )}
                  </div>
                </div>
              </article>
            );
          })}
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
              <button
                onClick={() => setIsUploadOpen(true)}
                className="btn-primary"
              >
                <FiPlus /> Ersten Vertrag hochladen
              </button>
            ) : undefined
          }
        />
      )}

      <UploadModal
        isOpen={isUploadOpen}
        onClose={() => {
          setIsUploadOpen(false);
          setEditingContract(null);
        }}
        initialData={editingContract}
        documentType="contract"
      />
      <ContractChat
        isOpen={!!chatContract}
        onClose={() => setChatContract(null)}
        contractId={chatContract?.id || 0}
        contractTitle={chatContract?.title || ""}
      />
      <AddToListModal
        isOpen={!!listContract}
        onClose={() => setListContract(null)}
        contract={listContract}
      />
      <AuditModal
        isOpen={!!auditContract}
        onClose={() => setAuditContract(null)}
        contractId={auditContract?.id || null}
        contractTitle={auditContract?.title || ""}
      />
      <ContractDetailsModal
        contract={detailsContract}
        onClose={() => setDetailsContract(null)}
        onDownload={handleDownload}
        onEdit={(contract) => {
          setDetailsContract(null);
          setEditingContract(contract);
          setIsUploadOpen(true);
        }}
      />
    </div>
  );
};

export default Contracts;
