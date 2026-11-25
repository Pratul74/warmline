import { API_BASE_URL, apiFetch } from "./client.js";

export const MAX_UPLOAD_BYTES = 1024 * 1024;


export const TEMPLATE_URL = `${API_BASE_URL}/faq/template.csv`;

export function uploadFaqCsv(token, file) {
  const form = new FormData();
  form.append("file", file);
  return apiFetch("/faq/upload", { method: "POST", token, body: form });
}

export function listFaqEntries(token, page, pageSize) {
  return apiFetch(`/faq?page=${page}&page_size=${pageSize}`, { token });
}
