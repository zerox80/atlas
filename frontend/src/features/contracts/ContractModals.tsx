import React from "react";
import AddToListModal from "../../components/AddToListModal";
import AuditModal from "../../components/AuditModal";
import ContractChat from "../../components/ContractChat";
import ContractDetailsModal from "../../components/ContractDetailsModal";
import UploadModal from "../../components/UploadModal";
import type { Contract } from "../../types";

interface ContractModalsProps {
  auditContract: Contract | null;
  chatContract: Contract | null;
  detailsContract: Contract | null;
  editingContract: Contract | null;
  isUploadOpen: boolean;
  listContract: Contract | null;
  onAuditClose: () => void;
  onChatClose: () => void;
  onDetailsClose: () => void;
  onDownload: (contract: Contract) => void | Promise<void>;
  onEdit: (contract: Contract) => void;
  onListClose: () => void;
  onUploadClose: () => void;
}

const ContractModals: React.FC<ContractModalsProps> = ({
  auditContract,
  chatContract,
  detailsContract,
  editingContract,
  isUploadOpen,
  listContract,
  onAuditClose,
  onChatClose,
  onDetailsClose,
  onDownload,
  onEdit,
  onListClose,
  onUploadClose,
}) => (
  <>
    <UploadModal
      isOpen={isUploadOpen}
      onClose={onUploadClose}
      initialData={editingContract}
      documentType="contract"
    />
    <ContractChat
      isOpen={Boolean(chatContract)}
      onClose={onChatClose}
      contractId={chatContract?.id || 0}
      contractTitle={chatContract?.title || ""}
    />
    <AddToListModal
      isOpen={Boolean(listContract)}
      onClose={onListClose}
      contract={listContract}
    />
    <AuditModal
      isOpen={Boolean(auditContract)}
      onClose={onAuditClose}
      contractId={auditContract?.id || null}
      contractTitle={auditContract?.title || ""}
    />
    <ContractDetailsModal
      contract={detailsContract}
      onClose={onDetailsClose}
      onDownload={onDownload}
      onEdit={onEdit}
    />
  </>
);

export default ContractModals;
