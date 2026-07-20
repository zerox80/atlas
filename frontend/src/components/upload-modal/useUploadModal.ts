import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useDropzone, type FileRejection } from "react-dropzone";
import api from "../../api";
import { useUser } from "../../App";
import { invalidateDocumentAndTagQueries, queryKeys } from "../../queryKeys";
import type { ContractAnalysisResult, ContractList } from "../../types";
import { dateInputToApiDate } from "../../utils/apiDate";
import { businessDateKey } from "../../utils/contractPresentation";
import { getApiErrorMessage } from "../../utils/errorUtils";
import { formatGermanNumber, parseGermanNumber } from "../../utils/formatUtils";
import {
  ACCEPTED_UPLOAD_TYPES,
  formatUploadSize,
  MAX_UPLOAD_SIZE,
} from "../UploadSourcePanel";
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
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [value, setValue] = useState("");
  const [annualValue, setAnnualValue] = useState("");
  const [tags, setTags] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [noticePeriod, setNoticePeriod] = useState("");
  const [uploading, setUploading] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [fileError, setFileError] = useState("");
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
    setStartDate(
      dateForInput(initialData?.start_date, initialData?.business_timezone),
    );
    setEndDate(
      dateForInput(initialData?.end_date, initialData?.business_timezone),
    );
    setFile(null);
    setFileError("");
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

  const onDrop = useCallback((acceptedFiles: File[]) => {
    if (!acceptedFiles.length) return;
    setFileError("");
    setFile(acceptedFiles[0]);
  }, []);

  const onDropRejected = useCallback((rejections: FileRejection[]) => {
    const firstError = rejections[0]?.errors[0];
    if (!firstError) return;
    if (firstError.code === "file-too-large") {
      setFileError(
        `Die Datei darf maximal ${formatUploadSize(MAX_UPLOAD_SIZE)} groß sein.`,
      );
    } else if (firstError.code === "file-invalid-type") {
      setFileError("Bitte laden Sie eine PDF-, Bild- oder Textdatei hoch.");
    } else {
      setFileError(firstError.message);
    }
    setFile(null);
  }, []);

  const dropzone = useDropzone({
    onDrop,
    onDropRejected,
    accept: ACCEPTED_UPLOAD_TYPES,
    maxFiles: 1,
    maxSize: MAX_UPLOAD_SIZE,
  });

  const handleAnalyze = async () => {
    if (!file) return;
    if (!file.name.toLowerCase().endsWith(".pdf")) {
      alert("KI-Analyse funktioniert nur mit PDF-Dateien.");
      return;
    }
    setAnalyzing(true);
    try {
      const formData = new FormData();
      formData.append("file", file);
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
      if (data.tags?.length) setTags(data.tags.join(", "));
    } catch (error: unknown) {
      alert(
        `KI-Analyse fehlgeschlagen: ${getApiErrorMessage(error, "Unbekannter Fehler")}`,
      );
    } finally {
      setAnalyzing(false);
    }
  };

  const resetAndClose = () => {
    setFile(null);
    setTitle("");
    setDescription("");
    setValue("");
    setAnnualValue("");
    setTags("");
    setNoticePeriod("");
    setStartDate("");
    setEndDate("");
    setFileError("");
    onClose();
  };

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
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
      resetAndClose();
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
    dropzone,
    endDate,
    file,
    fileError,
    handleAnalyze,
    handleSubmit,
    isEditing: Boolean(initialData),
    isInvoice,
    noticePeriod,
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
