export const triggerBlobDownload = (blob: Blob, filename: string): void => {
  const objectUrl = URL.createObjectURL(blob);
  const downloadLink = document.createElement("a");
  downloadLink.href = objectUrl;
  downloadLink.download = filename;
  downloadLink.style.display = "none";

  try {
    document.body.appendChild(downloadLink);
    downloadLink.click();
  } finally {
    downloadLink.remove();
    URL.revokeObjectURL(objectUrl);
  }
};
