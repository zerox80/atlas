import type { Contract } from "../../types";

export const getListIdFromSearchParams = (
  searchParams: URLSearchParams,
): number | null => {
  const listIdParam = searchParams.get("list_id");
  return listIdParam && /^\d+$/.test(listIdParam) ? Number(listIdParam) : null;
};

export const withWorkspacePath = (
  path: string,
  listId: number | null,
): string => {
  const [pathname, rawSearch = ""] = path.split("?");
  const searchParams = new URLSearchParams(rawSearch);

  if (listId !== null) searchParams.set("list_id", String(listId));
  else searchParams.delete("list_id");

  const search = searchParams.toString();
  return `${pathname}${search ? `?${search}` : ""}`;
};

export const matchesDocumentSearch = (
  document: Contract,
  searchQuery: string,
): boolean =>
  `${document.title} ${document.description || ""} ${document.tags
    .map((tag) => tag.name)
    .join(" ")}`
    .toLowerCase()
    .includes(searchQuery.toLowerCase());

export const getDocumentDownloadFilename = (document: Contract): string => {
  const extension = document.file_extension?.startsWith(".")
    ? document.file_extension
    : `.${document.file_extension || "pdf"}`;

  return document.title.endsWith(extension)
    ? document.title
    : `${document.title}${extension}`;
};
