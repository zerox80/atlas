import React, { useMemo } from "react";
import { useInfiniteQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import {
  FiAlertCircle,
  FiArrowUpRight,
  FiLock,
  FiShield,
  FiUnlock,
} from "react-icons/fi";
import {
  fetchContractPage,
  type ContractCursor,
  toggleContractProtection,
} from "../api";
import type { Contract, ContractPage } from "../types";
import { EmptyState, LoadingState, PageHeader } from "../components/ui";
import { getApiErrorMessage } from "../utils/errorUtils";
import { invalidateDocumentQueries, queryKeys } from "../queryKeys";
import { formatContractDate } from "../utils/contractPresentation";

const money = (value?: number | null) =>
  value == null
    ? "–"
    : value.toLocaleString("de-DE", { style: "currency", currency: "EUR" });

const ProtectedContracts: React.FC = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const {
    data: contractPages,
    error,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
    isLoading,
  } = useInfiniteQuery<ContractPage, unknown>(
    queryKeys.protectedContractPage,
    ({ pageParam }) =>
      fetchContractPage(
        { is_protected: true, limit: 48 },
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
  const contracts = useMemo(
    () => contractPages?.pages.flatMap((page) => page.items) ?? [],
    [contractPages],
  );
  const protectedCount = contractPages?.pages[0]?.summary?.all ?? 0;

  const errorMessage = error
    ? getApiErrorMessage(
        error,
        "Geschützte Dokumente konnten nicht geladen werden.",
      )
    : null;

  const handleUnprotect = async (contract: Contract) => {
    if (contract.version === undefined) {
      alert("Die Dokumentversion fehlt. Bitte lade die Ansicht neu.");
      return;
    }
    if (!window.confirm(`Schutz für „${contract.title}“ wirklich aufheben?`))
      return;
    try {
      await toggleContractProtection(contract.id, contract.version);
      await invalidateDocumentQueries(queryClient);
    } catch (mutationError: unknown) {
      alert(
        getApiErrorMessage(
          mutationError,
          "Der Schutzstatus konnte nicht geändert werden.",
        ),
      );
    }
  };

  if (isLoading)
    return <LoadingState label="Geschützte Dokumente werden geladen" />;

  return (
    <div className="app-page">
      <PageHeader
        eyebrow="Security / Vault"
        title="Protected Vault"
        description="Ein kontrollierter Bereich für Dokumente mit Löschschutz und erhöhten Zugriffsanforderungen."
        actions={
          <span className="chip border-emerald-300/20 bg-emerald-300/[0.07] text-emerald-200">
            <FiShield /> {protectedCount} geschützt
          </span>
        }
      />

      <section className="mb-5 flex gap-4 rounded-3xl border border-[#7397ff]/15 bg-[#7397ff]/[0.045] p-5">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-[#7397ff]/10 text-[#9ab1ff]">
          <FiAlertCircle />
        </div>
        <div>
          <h2 className="text-sm font-semibold">Löschschutz ist aktiv</h2>
          <p className="mt-1 max-w-3xl text-sm leading-6 text-white/43">
            Geschützte Dokumente können nicht gelöscht werden. Berechtigte
            Nutzer müssen den Schutz hier bewusst aufheben, bevor eine Löschung
            möglich wird.
          </p>
        </div>
      </section>

      {errorMessage && (
        <div className="mb-5 rounded-2xl border border-rose-400/20 bg-rose-400/[0.07] px-4 py-3 text-sm text-rose-200">
          {errorMessage}
        </div>
      )}

      {contracts.length ? (
        <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {contracts.map((contract) => (
            <article
              key={contract.id}
              className="surface-interactive group relative overflow-hidden p-6"
            >
              <div
                className={[
                  "absolute right-4 top-4 flex h-9 w-9 items-center justify-center",
                  "rounded-2xl border border-emerald-300/15 bg-emerald-300/[0.07]",
                  "text-emerald-200",
                ].join(" ")}
              >
                <FiLock />
              </div>
              <p className="eyebrow">
                {contract.document_type === "invoice"
                  ? "Protected invoice"
                  : "Protected contract"}
              </p>
              <h2 className="mt-3 max-w-[82%] truncate text-xl font-semibold tracking-[-0.025em]">
                {contract.title}
              </h2>
              <p className="mt-2 min-h-10 line-clamp-2 text-sm leading-5 text-white/40">
                {contract.description || "Keine Beschreibung hinterlegt."}
              </p>
              <div className="my-5 h-px bg-white/[0.07]" />
              <dl className="grid grid-cols-2 gap-4">
                <div>
                  <dt className="eyebrow">Wert</dt>
                  <dd className="mt-2 text-sm font-semibold">
                    {money(contract.value)}
                  </dd>
                </div>
                <div>
                  <dt className="eyebrow">Laufzeitende</dt>
                  <dd className="mt-2 text-sm font-semibold">
                    {contract.end_date
                      ? formatContractDate(contract.end_date, contract.business_timezone)
                      : "Unbefristet"}
                  </dd>
                </div>
              </dl>
              <div className="mt-6">
                {contract.can_manage_protection ? (
                  <button
                    onClick={() => handleUnprotect(contract)}
                    className="btn-secondary w-full hover:border-rose-300/25 hover:text-rose-200"
                  >
                    <FiUnlock /> Schutz aufheben
                  </button>
                ) : (
                  <div
                    className={[
                      "rounded-xl border border-white/[0.07] bg-black/20 px-3 py-2 text-center",
                      "text-xs text-white/32",
                    ].join(" ")}
                  >
                    Vollzugriff zum Entsperren erforderlich
                  </div>
                )}
              </div>
            </article>
          ))}
        </section>
      ) : errorMessage ? null : (
        <EmptyState
          icon={FiShield}
          title="Der Vault ist leer"
          description="Aktuell ist kein Dokument mit Löschschutz versehen."
          action={
            <button
              onClick={() => navigate("/contracts")}
              className="btn-secondary"
            >
              Zu den Verträgen <FiArrowUpRight />
            </button>
          }
        />
      )}

      {hasNextPage && (
        <div className="mt-5 flex justify-center">
          <button
            className="btn-secondary"
            disabled={isFetchingNextPage}
            onClick={() => void fetchNextPage()}
          >
            {isFetchingNextPage ? "Weitere Dokumente werden geladen…" : "Mehr Dokumente laden"}
          </button>
        </div>
      )}
    </div>
  );
};

export default ProtectedContracts;
