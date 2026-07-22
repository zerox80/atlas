import React, { useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  FiChevronLeft,
  FiChevronRight,
  FiFileText,
  FiFolder,
  FiRefreshCw,
  FiRotateCcw,
  FiSearch,
  FiTrash2,
} from "react-icons/fi";
import api from "../../api";
import { EmptyState } from "../../components/ui";
import { useDebouncedValue } from "../../hooks/useDebouncedValue";
import {
  invalidateListAndDocumentQueries,
  queryKeys,
} from "../../queryKeys";
import type {
  Contract,
  ContractList,
  DocumentType,
  TrashDocumentPage,
} from "../../types";
import { parseApiDate } from "../../utils/apiDate";
import { getApiErrorMessage } from "../../utils/errorUtils";

const PAGE_SIZE = 50;

interface TrashBrowserProps {
  adminView?: boolean;
  listId: number | null;
}

const workspaceLabel = (workspace: ContractList) =>
  workspace.is_default
    ? `Workspace${workspace.owner_username ? ` · ${workspace.owner_username}` : ""}`
    : workspace.name;

const documentLabel = (documentType: DocumentType) =>
  documentType === "invoice" ? "Rechnung" : "Vertrag";

const TrashBrowser: React.FC<TrashBrowserProps> = ({
  adminView = false,
  listId,
}) => {
  const queryClient = useQueryClient();
  const [documentType, setDocumentType] = useState<"all" | DocumentType>(
    "all",
  );
  const [search, setSearch] = useState("");
  const [adminListId, setAdminListId] = useState<number | null>(null);
  const [offset, setOffset] = useState(0);
  const [busyDocumentId, setBusyDocumentId] = useState<number | null>(null);
  const debouncedSearch = useDebouncedValue(search.trim());
  const effectiveListId = adminView ? adminListId : listId;
  const isEnabled = adminView || effectiveListId !== null;

  const { data: workspaces = [] } = useQuery<ContractList[]>(
    queryKeys.lists,
    async () => (await api.get<ContractList[]>("/lists")).data,
    { enabled: adminView, staleTime: 60_000 },
  );

  useEffect(() => {
    setOffset(0);
  }, [adminListId, debouncedSearch, documentType, listId]);

  const {
    data,
    isError,
    isFetching,
    isLoading,
    refetch,
  } = useQuery<TrashDocumentPage, unknown>(
    queryKeys.trashPage(
      effectiveListId,
      documentType,
      debouncedSearch,
      offset,
      adminView,
    ),
    async () =>
      (
        await api.get<TrashDocumentPage>("/trash", {
          params: {
            offset,
            limit: PAGE_SIZE,
            ...(effectiveListId !== null
              ? { list_id: effectiveListId }
              : {}),
            ...(documentType !== "all"
              ? { document_type: documentType }
              : {}),
            ...(debouncedSearch ? { q: debouncedSearch } : {}),
          },
        })
      ).data,
    {
      enabled: isEnabled,
      keepPreviousData: true,
    },
  );

  const items = data?.items ?? [];
  const total = data?.total ?? 0;
  const lastVisibleItem = Math.min(offset + items.length, total);
  const visibleWorkspace = useMemo(
    () => workspaces.find((workspace) => workspace.id === effectiveListId),
    [effectiveListId, workspaces],
  );

  const refreshAfterMutation = async () => {
    if (items.length === 1 && offset > 0) {
      setOffset(Math.max(0, offset - PAGE_SIZE));
    }
    await invalidateListAndDocumentQueries(queryClient);
  };

  const restoreDocument = async (document: Contract) => {
    if (document.version === undefined) {
      alert("Die Dokumentversion fehlt. Bitte lade den Papierkorb neu.");
      return;
    }
    setBusyDocumentId(document.id);
    try {
      await api.put(`/trash/${document.id}/restore`, null, {
        params: { version: document.version },
      });
      await refreshAfterMutation();
    } catch (error: unknown) {
      alert(
        getApiErrorMessage(
          error,
          `${documentLabel(document.document_type)} konnte nicht wiederhergestellt werden.`,
        ),
      );
    } finally {
      setBusyDocumentId(null);
    }
  };

  const permanentlyDeleteDocument = async (document: Contract) => {
    if (document.version === undefined) {
      alert("Die Dokumentversion fehlt. Bitte lade den Papierkorb neu.");
      return;
    }
    if (
      !window.confirm(
        `${documentLabel(document.document_type)} „${document.title}“ dauerhaft löschen? Datei und Daten können danach nicht wiederhergestellt werden.`,
      )
    ) {
      return;
    }
    setBusyDocumentId(document.id);
    try {
      await api.delete(`/trash/${document.id}/permanent`, {
        params: { version: document.version },
      });
      await refreshAfterMutation();
    } catch (error: unknown) {
      alert(
        getApiErrorMessage(
          error,
          `${documentLabel(document.document_type)} konnte nicht dauerhaft gelöscht werden.`,
        ),
      );
    } finally {
      setBusyDocumentId(null);
    }
  };

  if (!adminView && listId === null) {
    return (
      <EmptyState
        icon={FiFolder}
        title="Workspace auswählen"
        description="Wähle oben links einen Workspace aus. Jeder Workspace hat seinen eigenen Papierkorb für Verträge und Rechnungen."
      />
    );
  }

  return (
    <section>
      {adminView && (
        <div className="mb-5">
          <p className="eyebrow">Globale Wiederherstellung</p>
          <h2 className="section-title mt-2">Allgemeiner Papierkorb</h2>
          <p className="mt-2 max-w-3xl text-sm leading-6 muted">
            Gelöschte Verträge und Rechnungen aus allen Workspaces zentral
            wiederherstellen oder endgültig entfernen.
          </p>
        </div>
      )}

      <div className="surface mb-5 grid gap-3 p-3 lg:grid-cols-[minmax(0,1fr)_190px_240px_auto]">
        <label className="relative block">
          <span className="sr-only">Papierkorb durchsuchen</span>
          <FiSearch className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-white/30" />
          <input
            type="search"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            className="field w-full pl-10"
            placeholder="Gelöschte Dokumente suchen …"
          />
        </label>
        <label>
          <span className="sr-only">Dokumenttyp</span>
          <select
            value={documentType}
            onChange={(event) =>
              setDocumentType(event.target.value as "all" | DocumentType)
            }
            className="field w-full"
          >
            <option value="all">Verträge & Rechnungen</option>
            <option value="contract">Nur Verträge</option>
            <option value="invoice">Nur Rechnungen</option>
          </select>
        </label>
        {adminView ? (
          <label>
            <span className="sr-only">Workspace</span>
            <select
              value={adminListId ?? ""}
              onChange={(event) =>
                setAdminListId(
                  event.target.value ? Number(event.target.value) : null,
                )
              }
              className="field w-full"
            >
              <option value="">Alle Workspaces</option>
              {workspaces.map((workspace) => (
                <option key={workspace.id} value={workspace.id}>
                  {workspaceLabel(workspace)}
                </option>
              ))}
            </select>
          </label>
        ) : (
          <div className="flex min-w-0 items-center rounded-xl border border-white/[0.07] bg-white/[0.025] px-3 text-sm text-white/55">
            <FiFolder className="mr-2 shrink-0" />
            <span className="truncate">
              {visibleWorkspace
                ? workspaceLabel(visibleWorkspace)
                : `Workspace #${effectiveListId}`}
            </span>
          </div>
        )}
        <button
          type="button"
          onClick={() => void refetch()}
          disabled={isFetching}
          className="btn-secondary justify-center disabled:opacity-50"
          title="Papierkorb aktualisieren"
        >
          <FiRefreshCw className={isFetching ? "animate-spin" : ""} />
          Aktualisieren
        </button>
      </div>

      {isLoading ? (
        <div className="surface p-8 text-center text-sm muted">
          Papierkorb wird geladen …
        </div>
      ) : isError ? (
        <EmptyState
          icon={FiTrash2}
          title="Papierkorb konnte nicht geladen werden"
          description="Bitte aktualisiere die Ansicht und versuche es erneut."
          action={
            <button className="btn-secondary" onClick={() => void refetch()}>
              Erneut versuchen
            </button>
          }
        />
      ) : items.length === 0 ? (
        <EmptyState
          icon={FiTrash2}
          title="Papierkorb ist leer"
          description={
            debouncedSearch || documentType !== "all"
              ? "Für diese Suche oder diesen Filter gibt es keine gelöschten Dokumente."
              : "Hier landen gelöschte Verträge und Rechnungen, bis sie wiederhergestellt oder dauerhaft entfernt werden."
          }
        />
      ) : (
        <div className="space-y-3">
          {items.map((document) => {
            const isBusy = busyDocumentId === document.id;
            const assignedWorkspaces = document.lists ?? [];
            return (
              <article
                key={document.id}
                className="surface grid gap-4 p-4 lg:grid-cols-[minmax(0,1fr)_minmax(180px,260px)_auto] lg:items-center"
              >
                <div className="flex min-w-0 items-start gap-3">
                  <span
                    className={[
                      "flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border",
                      document.document_type === "invoice"
                        ? "border-[#77a7ff]/20 bg-[#77a7ff]/10 text-[#77a7ff]"
                        : "border-[#b8f15a]/20 bg-[#b8f15a]/10 text-[#b8f15a]",
                    ].join(" ")}
                  >
                    <FiFileText />
                  </span>
                  <div className="min-w-0">
                    <div className="mb-1 flex flex-wrap items-center gap-2">
                      <span className="chip">
                        {documentLabel(document.document_type)}
                      </span>
                      <span className="text-[11px] text-white/32">
                        Gelöscht am{" "}
                        {document.deleted_at
                          ? parseApiDate(document.deleted_at).toLocaleString(
                              "de-DE",
                            )
                          : "–"}
                      </span>
                    </div>
                    <h3 className="truncate font-semibold text-white">
                      {document.title}
                    </h3>
                    {adminView && (
                      <p className="mt-1 truncate text-xs muted">
                        Gelöscht von {document.deleted_by_username || "Unbekannt"}
                      </p>
                    )}
                  </div>
                </div>

                <div className="min-w-0">
                  <p className="mb-1 text-[10px] font-bold uppercase tracking-[.12em] text-white/28">
                    Workspaces
                  </p>
                  <p className="truncate text-sm text-white/55">
                    {assignedWorkspaces.length
                      ? assignedWorkspaces.map(workspaceLabel).join(", ")
                      : "Keine Zuordnung"}
                  </p>
                </div>

                <div className="flex flex-wrap gap-2 lg:justify-end">
                  {document.can_delete ? (
                    <>
                      <button
                        type="button"
                        onClick={() => void restoreDocument(document)}
                        disabled={isBusy}
                        className="btn-secondary disabled:opacity-50"
                      >
                        <FiRotateCcw /> Wiederherstellen
                      </button>
                      <button
                        type="button"
                        onClick={() => void permanentlyDeleteDocument(document)}
                        disabled={isBusy}
                        className="btn-ghost text-rose-300 hover:text-rose-200 disabled:opacity-50"
                      >
                        <FiTrash2 /> Dauerhaft löschen
                      </button>
                    </>
                  ) : (
                    <span className="chip">Nur ansehen</span>
                  )}
                </div>
              </article>
            );
          })}
        </div>
      )}

      {total > 0 && (
        <div className="mt-5 flex flex-wrap items-center justify-between gap-3 text-sm muted">
          <span>
            {offset + 1}–{lastVisibleItem} von {total}
          </span>
          <div className="flex gap-2">
            <button
              type="button"
              className="btn-secondary"
              disabled={offset === 0 || isFetching}
              onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
            >
              <FiChevronLeft /> Zurück
            </button>
            <button
              type="button"
              className="btn-secondary"
              disabled={offset + PAGE_SIZE >= total || isFetching}
              onClick={() => setOffset(offset + PAGE_SIZE)}
            >
              Weiter <FiChevronRight />
            </button>
          </div>
        </div>
      )}
    </section>
  );
};

export default TrashBrowser;
