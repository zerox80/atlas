import React, { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  FiArrowUpRight,
  FiEdit2,
  FiFileText,
  FiFolder,
  FiPlus,
  FiTrash2,
} from "react-icons/fi";
import { useNavigate } from "react-router-dom";
import api from "../api";
import { parseApiDate } from "../utils/apiDate";
import ListModal from "../components/ListModal";
import { useUser } from "../App";
import { EmptyState, LoadingState, PageHeader } from "../components/ui";
import type { ContractList } from "../types";
import { getApiErrorMessage } from "../utils/errorUtils";
import {
  invalidateListAndDocumentQueries,
  queryKeys,
} from "../queryKeys";

const Lists: React.FC = () => {
  const navigate = useNavigate();
  const { isAdmin } = useUser();
  const queryClient = useQueryClient();
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingList, setEditingList] = useState<ContractList | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  const { data: lists = [], isLoading } = useQuery<ContractList[]>(
    queryKeys.lists,
    async () => (await api.get<ContractList[]>("/lists")).data,
  );

  const openCreate = () => {
    setEditingList(null);
    setIsModalOpen(true);
  };

  const handleCreateOrEdit = async (data: {
    name: string;
    description: string;
    color: string;
  }) => {
    setIsSaving(true);
    try {
      if (editingList) await api.put(`/lists/${editingList.id}`, data);
      else await api.post("/lists", data);
      await invalidateListAndDocumentQueries(queryClient);
      setIsModalOpen(false);
      setEditingList(null);
    } catch (error: unknown) {
      alert(
        getApiErrorMessage(error, "Fehler beim Speichern der Sammlung"),
      );
    } finally {
      setIsSaving(false);
    }
  };

  const handleDelete = async (list: ContractList) => {
    if (
      !window.confirm(
        `Sammlung „${list.name}“ wirklich löschen? Die Dokumente bleiben erhalten.`,
      )
    )
      return;
    try {
      await api.delete(`/lists/${list.id}`);
      await invalidateListAndDocumentQueries(queryClient);
    } catch (error: unknown) {
      alert(getApiErrorMessage(error, "Fehler beim Löschen der Sammlung"));
    }
  };

  if (isLoading) return <LoadingState label="Sammlungen werden geladen" />;

  const totalDocuments = lists.reduce(
    (sum, list) => sum + list.contract_count,
    0,
  );

  return (
    <div className="app-page">
      <PageHeader
        eyebrow="Workspace / Collections"
        title="Sammlungen"
        description={[
          "Baue thematische Workspaces für Teams, Anbieter oder Projekte. Ein",
          "Dokument kann in mehreren Sammlungen leben.",
        ].join(" ")}
        actions={
          isAdmin ? (
            <button onClick={openCreate} className="btn-primary">
              <FiPlus /> Neue Sammlung
            </button>
          ) : undefined
        }
      />

      <section className="mb-5 grid gap-3 sm:grid-cols-3">
        <div className="surface p-5">
          <p className="eyebrow">Sammlungen</p>
          <p className="metric-value mt-3">{lists.length}</p>
        </div>
        <div className="surface p-5">
          <p className="eyebrow">Dokument-Verknüpfungen</p>
          <p className="metric-value mt-3">{totalDocuments}</p>
        </div>
        <div className="surface p-5">
          <p className="eyebrow">Arbeitsmodus</p>
          <p className="mt-3 text-xl font-semibold text-white">
            {isAdmin ? "Verwalten" : "Ansehen"}
          </p>
        </div>
      </section>

      {lists.length ? (
        <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {lists.map((list, index) => (
            <article
              key={list.id}
              className="surface-interactive group relative overflow-hidden p-6"
            >
              <div
                className="absolute inset-x-0 top-0 h-px"
                style={{
                  background: `linear-gradient(90deg, ${list.color}, transparent)`,
                }}
              />
              <div className="mb-8 flex items-start justify-between">
                <div
                  className="flex h-12 w-12 items-center justify-center rounded-2xl"
                  style={{
                    color: list.color,
                    backgroundColor: `${list.color}16`,
                    border: `1px solid ${list.color}30`,
                  }}
                >
                  <FiFolder size={22} />
                </div>
                {isAdmin && !list.is_default && (
                  <div className="flex gap-1 opacity-100 transition-opacity md:opacity-0 md:group-hover:opacity-100">
                    <button
                      onClick={() => {
                        setEditingList(list);
                        setIsModalOpen(true);
                      }}
                      className="icon-btn"
                      title="Bearbeiten"
                    >
                      <FiEdit2 />
                    </button>
                    <button
                      onClick={() => handleDelete(list)}
                      className="icon-btn hover:border-rose-400/30 hover:text-rose-300"
                      title="Löschen"
                    >
                      <FiTrash2 />
                    </button>
                  </div>
                )}
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <p className="eyebrow">
                  Collection {String(index + 1).padStart(2, "0")}
                </p>
                {list.is_preferred_default && (
                  <span className="chip border-[#b8f15a]/20 bg-[#b8f15a]/[0.07] text-[#b8f15a]">
                    Mein Standard
                  </span>
                )}
                {list.is_default && <span className="chip">Persönlich</span>}
              </div>
              <h2 className="mt-2 truncate text-xl font-semibold tracking-[-0.02em]">
                {list.name}
              </h2>
              {list.owner_username && (
                <p className="mt-1 text-xs text-white/34">
                  Eigentümer: {list.owner_username}
                </p>
              )}
              <p className="mt-2 min-h-10 line-clamp-2 text-sm leading-5 text-white/42">
                {list.description || "Noch keine Beschreibung hinterlegt."}
              </p>
              <div className="my-5 h-px bg-white/[0.07]" />
              <div className="mb-5 flex items-center justify-between text-xs text-white/36">
                <span className="flex items-center gap-2">
                  <FiFileText /> {list.contract_count} Dokumente
                </span>
                <span>
                  {parseApiDate(list.created_at).toLocaleDateString("de-DE")}
                </span>
              </div>
              <button
                onClick={() => navigate(`/?list_id=${list.id}`)}
                className="btn-secondary w-full justify-between"
              >
                Workspace öffnen <FiArrowUpRight />
              </button>
            </article>
          ))}
        </section>
      ) : (
        <EmptyState
          icon={FiFolder}
          title="Noch keine Sammlungen"
          description={
            isAdmin
              ? "Erstelle den ersten thematischen Workspace und ordne Dokumente gezielt zu."
              : "Für dich sind aktuell keine Sammlungen freigegeben."
          }
          action={
            isAdmin ? (
              <button onClick={openCreate} className="btn-primary">
                <FiPlus /> Erste Sammlung
              </button>
            ) : undefined
          }
        />
      )}

      <ListModal
        isOpen={isModalOpen}
        onClose={() => {
          setIsModalOpen(false);
          setEditingList(null);
        }}
        onSubmit={handleCreateOrEdit}
        initialData={editingList}
        isLoading={isSaving}
      />
    </div>
  );
};

export default Lists;
