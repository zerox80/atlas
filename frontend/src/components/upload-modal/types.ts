import type { Contract, DocumentType } from "../../types";

export interface UploadModalProps {
  isOpen: boolean;
  onClose: () => void;
  initialData?: Contract | null;
  initialListId?: number | null;
  documentType?: DocumentType;
}
