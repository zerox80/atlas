import { useEffect, useMemo, useState, type FormEvent } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import api from "../../api";
import { useUser } from "../../App";
import { invalidateDocumentAndTagQueries, queryKeys } from "../../queryKeys";
import type { ContractAnalysisResult, ContractList } from "../../types";
import { dateInputToApiDate } from "../../utils/apiDate";
import { businessDateKey } from "../../utils/contractPresentation";
import { getApiErrorMessage } from "../../utils/errorUtils";
import { formatGermanNumber, parseGermanNumber } from "../../utils/formatUtils";
import { useUploadFiles } from "./useUploadFiles";
import type { UploadModalProps } from "./types";

const dateForInput = (value?: string | null, timeZone?: string) => {
  if (!value) return "";
  return /^\d{4}-\d{2}-\d{2}$/.test(value)
    ? value
    : businessDateKey(value, timeZone);
};

export const useUploadModal = ({
  isOpen,
  onClose,
  initialData,
  initialListId,
  documentType = "contract",
}: UploadModalProps) => {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [value, setValue] = useState("");
  const [annualValue, setAnnualValue] = useState("");
  const [tags, setTags] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [noticePeriod, setNoticePeriod] = useState("");
  const [noticeEvidence, setNoticeEvidence] = useState<string | null>(null);
  const [analysisWarnings, setAnalysisWarnings] = useState<string[]>([]);
  const [uploading, setUploading] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const uploadFiles = useUploadFiles(isOpen, initialData, uploading || analyzing);
  const { file, attachments, attachmentIdsToRemove, selectedAnalysisFile } = uploadFiles;
  const [workspaceId, setWorkspaceId] = useState(0);
  const queryClient = useQueryClient();
  const { user } = useUser();

  const { data: availableWorkspaces = [], isLoading: workspacesLoading } =
    useQuery<ContractList[]>(
      queryKeys.lists,
      async () => (await api.get<ContractList[]>("/lists")).data,
      { enabled: isOpen && !initialData },
    );
  const writableWorkspaces = useMemo(
    () =>
      availableWorkspaces.filter(
        (workspace) =>
          workspace.can_write &&
          (!workspace.is_default || workspace.owner_user_id === user?.id),
      ),
    [availableWorkspaces, user?.id],
  );

  const isInvoice = (initialData?.document_type ?? documentType) === "invoice";
  const documentLabel = isInvoice ? "Rechnung" : "Vertrag";

  useEffect(() => {
    if (!isOpen) return;
    setTitle(initialData?.title || "");
    setDescription(initialData?.description || "");
    setValue(
      initialData?.value != null ? formatGermanNumber(initialData.value) : "",
    );
    setAnnualValue(
      initialData?.annual_value != null
        ? formatGermanNumber(initialData.annual_value)
        : "",
    );
    setTags(initialData?.tags.map((tag) => tag.name).join(", ") || "");
    setNoticePeriod(initialData?.notice_period?.toString() || "");
    setNoticeEvidence(null);
    setAnalysisWarnings([]);
    setStartDate(
      dateForInput(initialData?.start_date, initialData?.business_timezone),
    );
    setEndDate(
      dateForInput(initialData?.end_date, initialData?.business_timezone),
    );
  }, [isOpen, initialData]);

  useEffect(() => {
    if (!isOpen || initialData) return;
    const requested = writableWorkspaces.find(
      (workspace) => workspace.id === initialListId,
    );
    const preferred = writableWorkspaces.find(
      (workspace) =>
        workspace.id === user?.default_workspace_id ||
        workspace.is_preferred_default,
    );
    const personal = writableWorkspaces.find(
      (workspace) =>
        workspace.is_default && workspace.owner_user_id === user?.id,
    );
    setWorkspaceId(
      requested?.id ?? preferred?.id ?? personal?.id ?? 0,
    );
  }, [
    initialData,
    initialListId,
    isOpen,
    user?.default_workspace_id,
    user?.id,
    writableWorkspaces,
  ]);

  const handleAnalyze = async () => {
    if (!selectedAnalysisFile || analyzing || uploading) return;
    setAnalyzing(true);
    try {
      const formData = new FormData();
      formData.append("file", selectedAnalysisFile);
      formData.append("document_type", isInvoice ? "invoice" : "contract");
      const { data } = await api.post<ContractAnalysisResult>(
        "/contracts/analyze",
        formData,
        { headers: { "Content-Type": "multipart/form-data" } },
      );
      if (data.title) setTitle(data.title);
      if (data.description) setDescription(data.description);
      if (data.value != null) setValue(formatGermanNumber(data.value));
      if (data.annual_value != null) {
        setAnnualValue(formatGermanNumber(data.annual_value));
      }
      if (data.start_date) setStartDate(dateForInput(data.start_date));
      if (data.end_date) setEndDate(dateForInput(data.end_date));
      setNoticePeriod(
        data.notice_period != null ? data.notice_period.toString() : "",
      );
      setNoticeEvidence(data.notice_period_evidence || null);
      setAnalysisWarnings(data.analysis_warnings || []);
      if (data.tags?.length) setTags(data.tags.join(", "));
    } catch (error: unknown) {
      alert(
        `KI-Analyse fehlgeschlagen: ${getApiErrorMessage(error, "Unbekannter Fehler")}`,
      );
    } finally {
      setAnalyzing(false);
    }
  };

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (uploading || analyzing) return;
    if ((!initialData && !file) || !title) return;
    if (!initialData && workspaceId === 0) {
      alert("Es ist kein beschreibbarer Workspace als Ablageziel verfügbar.");
      return;
    }
    setUploading(true);
    try {
      const parsedValue = value ? parseGermanNumber(value) : null;
      const parsedAnnualValue = annualValue
        ? parseGermanNumber(annualValue)
        : null;
      if (value && (parsedValue === null || parsedValue < 0)) {
        alert("Bitte geben Sie einen gültigen nicht-negativen Gesamtwert ein.");
        return;
      }
      if (
        annualValue &&
        (parsedAnnualValue === null || parsedAnnualValue < 0)
      ) {
        alert(
          "Bitte geben Sie einen gültigen nicht-negativen jährlichen Preis ein.",
        );
        return;
      }

      const formData = new FormData();
      if (file) formData.append("file", file);
      attachments.forEach((attachment) => formData.append("attachments", attachment));
      attachmentIdsToRemove.forEach((id) => formData.append("removed_attachment_ids", id.toString()));
      formData.append("title", title);
      formData.append("description", description || "");
      formData.append("value", parsedValue !== null ? parsedValue.toString() : "");
      formData.append(
        "annual_value",
        parsedAnnualValue !== null ? parsedAnnualValue.toString() : "",
      );
      formData.append("notice_period", noticePeriod || "");
      formData.append("tags", tags || "");
      formData.append("start_date", dateInputToApiDate(startDate));
      formData.append("end_date", dateInputToApiDate(endDate));
      if (!initialData) {
        formData.append("document_type", isInvoice ? "invoice" : "contract");
        formData.append("list_id", workspaceId.toString());
      } else {
        if (initialData.version === undefined) {
          throw new Error("Die Dokumentversion fehlt. Bitte lade die Ansicht neu.");
        }
        formData.append("version", initialData.version.toString());
      }

      if (initialData) {
        await api.put(`/contracts/${initialData.id}`, formData, {
          headers: { "Content-Type": "multipart/form-data" },
        });
      } else {
        await api.post("/contracts", formData, {
          headers: { "Content-Type": "multipart/form-data" },
        });
      }

      await invalidateDocumentAndTagQueries(queryClient);
      onClose();
    } catch (error: unknown) {
      alert(
        `Vorgang fehlgeschlagen: ${getApiErrorMessage(error, "Unbekannter Fehler")}`,
      );
    } finally {
      setUploading(false);
    }
  };

  return {
    analyzing,
    annualValue,
    description,
    documentLabel,
    uploadFiles,
    endDate,
    file,
    handleAnalyze,
    handleSubmit,
    isEditing: Boolean(initialData),
    isInvoice,
    noticePeriod,
    noticeEvidence,
    analysisWarnings,
    setAnnualValue,
    setDescription,
    setEndDate,
    setNoticePeriod,
    setStartDate,
    setTags,
    setTitle,
    setValue,
    setWorkspaceId,
    startDate,
    tags,
    title,
    uploading,
    value,
    workspaceId,
    workspacesLoading,
    writableWorkspaces,
  };
};

export type UploadModalController = ReturnType<typeof useUploadModal>;
