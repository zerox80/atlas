import api from "../../api";
import type { Contract } from "../../types";
import { triggerBlobDownload } from "../../utils/downloadUtils";
import { getDocumentDownloadFilename } from "./documentUtils";

export const downloadDocument = async (document: Contract): Promise<void> => {
  const response = await api.get<Blob>(`/contracts/${document.id}/download`, {
    responseType: "blob",
  });

  triggerBlobDownload(response.data, getDocumentDownloadFilename(document));
};
