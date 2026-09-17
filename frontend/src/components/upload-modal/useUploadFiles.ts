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

export const describeFileRejections = (rejections: FileRejection[]) =>
  rejections.map(({ file: rejected, errors: reasons }) => {
    const reason = reasons[0]?.code === "file-too-large"
      ? `maximal ${formatUploadSize(MAX_UPLOAD_SIZE)} pro Datei`
      : reasons[0]?.code === "file-too-small"
        ? "leere Dateien sind nicht erlaubt"
        : reasons[0]?.code === "too-many-files"
          ? "bitte genau eine Ersatzdatei auswählen"
          : "nur PDF, PNG, JPG oder TXT erlaubt";
    return `${rejected.name}: ${reason}.`;
  });

export const useUploadFiles = (
  isOpen: boolean,
  initialData: Contract | null | undefined,
  disabled: boolean,
) => {
  const [files, setFiles] = useState<File[]>([]);
  const [analysisFile, setAnalysisFile] = useState<File | null>(null);
  const [mainReplacement, setMainReplacement] = useState<File | null>(null);
  const [attachmentReplacements, setAttachmentReplacements] = useState<Record<number, File>>({});
  const [removedAttachmentIds, setRemovedAttachmentIds] = useState<number[]>([]);
  const [fileError, setFileError] = useState("");
  const existingAttachments = initialData?.attachments ?? [];
  const retainedCount = existingAttachments.length - removedAttachmentIds.length;
  const file = initialData ? mainReplacement : files[0] ?? null;
  const replacements = Object.values(attachmentReplacements);
  const attachments = [...(initialData ? files : files.slice(1)), ...replacements];
  const attachmentIdsToRemove = [
    ...removedAttachmentIds, ...Object.keys(attachmentReplacements).map(Number),
  ];
  const analysisFiles = [...(mainReplacement ? [mainReplacement] : []), ...files, ...replacements];
  const selectedAnalysisFile = analysisFile && analysisFiles.includes(analysisFile)
    ? analysisFile
    : analysisFiles.find((item) => item.name.toLowerCase().endsWith(".pdf")) ?? null;

  useEffect(() => {
    if (!isOpen) return;
    setFiles([]);
    setAnalysisFile(null);
    setMainReplacement(null);
    setAttachmentReplacements({});
    setRemovedAttachmentIds([]);
    setFileError("");
  }, [isOpen, initialData]);

  const onDrop = (acceptedFiles: File[], rejections: FileRejection[]) => {
    if (disabled) return;
    const errors = describeFileRejections(rejections);
    const nextFiles = [...files];
    const capacity = MAX_DOCUMENT_FILES - retainedCount - (initialData ? 1 : 0);
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
    minSize: 1,
    disabled,
  });

  const removeFile = (target: File) => {
    if (disabled) return;
    setFiles((current) => current.filter((item) => item !== target));
    setFileError("");
  };
  const makePrimary = (target: File) => {
    if (disabled) return;
    if (initialData) {
      setMainReplacement(target);
      setFiles((current) => current.filter((item) => item !== target));
    } else {
      setFiles((current) => [target, ...current.filter((item) => item !== target)]);
    }
    setFileError("");
  };
  const replaceMain = (replacement: File) => {
    if (disabled) return;
    setMainReplacement(replacement);
    setFileError("");
  };
  const keepAttachment = (id: number) => {
    if (disabled) return;
    setAttachmentReplacements((current) => {
      const next = { ...current };
      delete next[id];
      return next;
    });
    setFileError("");
  };
  const replaceAttachment = (id: number, replacement: File) => {
    if (disabled || removedAttachmentIds.includes(id)) return;
    setAttachmentReplacements((current) => ({ ...current, [id]: replacement }));
    setFileError("");
  };
  const toggleAttachmentRemoval = (id: number) => {
    if (disabled) return;
    if (removedAttachmentIds.includes(id) && 1 + retainedCount + files.length >= MAX_DOCUMENT_FILES) {
      setFileError(`Maximal ${MAX_DOCUMENT_FILES} Dateien pro Dokument.`);
      return;
    }
    setRemovedAttachmentIds((current) => current.includes(id)
      ? current.filter((item) => item !== id) : [...current, id]);
    keepAttachment(id);
  };
  const keepOriginal = () => {
    if (disabled) return;
    setMainReplacement(null);
    setFileError("");
  };

  return {
    file, files, attachments, fileError, dropzone, selectedAnalysisFile, analysisFiles,
    existingAttachments, removedAttachmentIds, attachmentIdsToRemove, attachmentReplacements,
    setAnalysisFile, setFileError, removeFile, makePrimary, toggleAttachmentRemoval,
    replaceMain, replaceAttachment, keepOriginal, keepAttachment,
  };
};

export type UploadFilesController = ReturnType<typeof useUploadFiles>;
