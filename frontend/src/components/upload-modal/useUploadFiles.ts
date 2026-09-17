import { useEffect, useState } from "react";
import { useDropzone, type FileRejection } from "react-dropzone";
import type { Contract } from "../../types";

export const MAX_UPLOAD_SIZE = 10 * 1024 * 1024;
export const MAX_DOCUMENT_FILES = 10;
export const ACCEPTED_UPLOAD_TYPES = {
  "application/pdf": [".pdf"],
  "image/png": [".png"],
  "image/jpeg": [".jpg", ".jpeg"],
  "text/plain": [".txt"],
};
export const formatUploadSize = (bytes: number) =>
  bytes < 1024 ? `${bytes} B`
    : bytes < 1024 * 1024 ? `${Number((bytes / 1024).toFixed(1))} KB`
      : `${Number((bytes / 1024 / 1024).toFixed(1))} MB`;

const sameFile = (left: File, right: File) =>
  left.name === right.name && left.size === right.size && left.lastModified === right.lastModified;

export const useUploadFiles = (
  isOpen: boolean,
  initialData: Contract | null | undefined,
  disabled: boolean,
) => {
  const [files, setFiles] = useState<File[]>([]);
  const [analysisFile, setAnalysisFile] = useState<File | null>(null);
  const [replaceMain, setReplaceMain] = useState(false);
  const [removedAttachmentIds, setRemovedAttachmentIds] = useState<number[]>([]);
  const [fileError, setFileError] = useState("");
  const existingAttachments = initialData?.attachments ?? [];
  const retainedCount = existingAttachments.length - removedAttachmentIds.length;
  const file = !initialData || replaceMain ? files[0] ?? null : null;
  const attachments = file ? files.slice(1) : files;
  const selectedAnalysisFile = analysisFile && files.includes(analysisFile)
    ? analysisFile
    : files.find((item) => item.name.toLowerCase().endsWith(".pdf")) ?? null;

  useEffect(() => {
    if (!isOpen) return;
    setFiles([]);
    setAnalysisFile(null);
    setReplaceMain(false);
    setRemovedAttachmentIds([]);
    setFileError("");
  }, [isOpen, initialData]);

  const onDrop = (acceptedFiles: File[], rejections: FileRejection[]) => {
    const errors = rejections.map(({ file: rejected, errors: reasons }) => {
      const reason = reasons[0]?.code === "file-too-large"
        ? `maximal ${formatUploadSize(MAX_UPLOAD_SIZE)} pro Datei`
        : "nur PDF, PNG, JPG oder TXT erlaubt";
      return `${rejected.name}: ${reason}.`;
    });
    const nextFiles = [...files];
    const capacity = MAX_DOCUMENT_FILES - retainedCount - (initialData && !replaceMain ? 1 : 0);
    for (const candidate of acceptedFiles) {
      if (nextFiles.some((existing) => sameFile(existing, candidate))) continue;
      if (nextFiles.length >= capacity) {
        errors.push(`Maximal ${MAX_DOCUMENT_FILES} Dateien pro Dokument. ${candidate.name} wurde nicht hinzugefügt.`);
      } else {
        nextFiles.push(candidate);
      }
    }
    setFiles(nextFiles);
    setFileError(errors.join(" "));
  };

  const dropzone = useDropzone({
    onDrop,
    accept: ACCEPTED_UPLOAD_TYPES,
    multiple: true,
    maxSize: MAX_UPLOAD_SIZE,
    disabled,
  });

  const removeFile = (target: File) => {
    if (disabled) return;
    setFiles((current) => current.filter((item) => item !== target));
    setFileError("");
  };
  const makePrimary = (target: File) => {
    if (disabled) return;
    setFiles((current) => [target, ...current.filter((item) => item !== target)]);
    if (initialData) setReplaceMain(true);
    setFileError("");
  };
  const toggleAttachmentRemoval = (id: number) => {
    if (disabled) return;
    if (removedAttachmentIds.includes(id) && 1 + retainedCount + attachments.length >= MAX_DOCUMENT_FILES) {
      setFileError(`Maximal ${MAX_DOCUMENT_FILES} Dateien pro Dokument.`);
      return;
    }
    setRemovedAttachmentIds((current) => current.includes(id)
      ? current.filter((item) => item !== id) : [...current, id]);
    setFileError("");
  };
  const keepOriginal = () => {
    if (1 + retainedCount + files.length > MAX_DOCUMENT_FILES) {
      setFileError(`Maximal ${MAX_DOCUMENT_FILES} Dateien pro Dokument. Entferne zuerst eine neue Datei.`);
      return;
    }
    setReplaceMain(false);
  };

  return {
    file, files, attachments, fileError, dropzone, selectedAnalysisFile,
    existingAttachments, removedAttachmentIds, replaceMain,
    setAnalysisFile, removeFile, makePrimary, toggleAttachmentRemoval, keepOriginal,
  };
};

export type UploadFilesController = ReturnType<typeof useUploadFiles>;
