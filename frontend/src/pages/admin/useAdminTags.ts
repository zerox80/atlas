import { useState } from "react";
import type { FormEventHandler } from "react";
import { useQueryClient } from "@tanstack/react-query";
import api from "../../api";
import { invalidateDocumentQueries, queryKeys } from "../../queryKeys";
import { getApiErrorMessage } from "../../utils/errorUtils";
import type { Tag } from "./types";

type ReloadAdminData = () => Promise<void>;

export const useAdminTags = (loadData: ReloadAdminData) => {
  const queryClient = useQueryClient();
  const [isAddTagModalOpen, setIsAddTagModalOpen] = useState(false);
  const [isEditTagModalOpen, setIsEditTagModalOpen] = useState(false);
  const [selectedTag, setSelectedTag] = useState<Tag | null>(null);
  const [newTagName, setNewTagName] = useState("");
  const [newTagColor, setNewTagColor] = useState("#3b82f6");
  const [editTagName, setEditTagName] = useState("");
  const [editTagColor, setEditTagColor] = useState("#3b82f6");

  const handleAddTag: FormEventHandler<HTMLFormElement> = async (event) => {
    event.preventDefault();
    try {
      await api.post("/tags", { name: newTagName, color: newTagColor });
      setNewTagName("");
      setNewTagColor("#3b82f6");
      setIsAddTagModalOpen(false);
      await Promise.all([queryClient.invalidateQueries(queryKeys.tags), loadData()]);
    } catch (error: unknown) {
      alert(getApiErrorMessage(error, "Fehler beim Erstellen"));
    }
  };

  const openEditTag = (tag: Tag) => {
    setSelectedTag(tag);
    setEditTagName(tag.name);
    setEditTagColor(tag.color);
    setIsEditTagModalOpen(true);
  };

  const handleUpdateTag: FormEventHandler<HTMLFormElement> = async (event) => {
    event.preventDefault();
    if (!selectedTag) return;
    try {
      await api.put(`/tags/${selectedTag.id}`, {
        name: editTagName,
        color: editTagColor,
      });
      setIsEditTagModalOpen(false);
      setSelectedTag(null);
      await Promise.all([
        queryClient.invalidateQueries(queryKeys.tags),
        invalidateDocumentQueries(queryClient),
        loadData(),
      ]);
    } catch (error: unknown) {
      alert(getApiErrorMessage(error, "Fehler beim Aktualisieren"));
    }
  };

  const handleDeleteTag = async (tagId: number) => {
    if (!confirm("Tag wirklich löschen? Er wird von allen Verträgen entfernt.")) {
      return;
    }
    try {
      await api.delete(`/tags/${tagId}`);
      await Promise.all([
        queryClient.invalidateQueries(queryKeys.tags),
        invalidateDocumentQueries(queryClient),
        loadData(),
      ]);
    } catch (error: unknown) {
      alert(getApiErrorMessage(error, "Fehler beim Löschen"));
    }
  };

  return {
    editTagColor,
    editTagName,
    handleAddTag,
    handleDeleteTag,
    handleUpdateTag,
    isAddTagModalOpen,
    isEditTagModalOpen,
    newTagColor,
    newTagName,
    openEditTag,
    selectedTag,
    setEditTagColor,
    setEditTagName,
    setIsAddTagModalOpen,
    setIsEditTagModalOpen,
    setNewTagColor,
    setNewTagName,
  };
};
