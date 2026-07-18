import type { Contract, DocumentType } from "../../types";

export interface UploadModalProps {
  isOpen: boolean;
  onClose: () => void;
  initialData?: Contract | null;
  documentType?: DocumentType;
}
