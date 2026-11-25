// FAQ entries: CSV upload, the paginated list and the sample template. Owner token needed,
// except for the template.
//
// An FAQ entry: {id, question, answer, created_at, updated_at}
import { API_BASE_URL, apiFetch } from "./client";

// A plain link works: the backend serves the template without login.
export const TEMPLATE_URL = `${API_BASE_URL}/faq/template.csv`;

// Sends the file as the multipart field "file". Returns {inserted, updated, unchanged}.
// A 422 throws an ApiError whose .errors holds the row problems: [{row, field, message}].
export function uploadFaqCsv(token, file) {
  const form = new FormData();
  form.append("file", file);
  return apiFetch("/faq/upload", { method: "POST", token, body: form });
}

// Returns {items: [FAQ entry], total, page, page_size}. page starts at 1.
export function listFaqEntries(token, page, pageSize) {
  return apiFetch(`/faq?page=${page}&page_size=${pageSize}`, { token });
}
