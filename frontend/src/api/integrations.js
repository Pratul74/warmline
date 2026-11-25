// Integrations: an owner's chat links. Every call needs the owner's token.
//
// An integration as the API returns it:
//   {id, public_id, embed_url, name, greeting (string or null),
//    status ("active" | "disabled"), created_at, disabled_at (or null)}
import { apiFetch } from "./client";

// Same limits as app/services/integrations.py.
export const MAX_NAME_LENGTH = 100;
export const MAX_GREETING_LENGTH = 500;

// Returns a list of integrations, oldest first.
export function listIntegrations(token) {
  return apiFetch("/integrations", { token });
}

// Returns the new integration. An empty greeting is sent as null (no greeting).
export function createIntegration(token, { name, greeting }) {
  return apiFetch("/integrations", {
    method: "POST",
    token,
    body: { name, greeting: greeting || null },
  });
}

// changes may hold name, greeting and/or enabled; only those are changed.
// An empty greeting clears it. Returns the updated integration.
export function updateIntegration(token, id, changes) {
  return apiFetch(`/integrations/${id}`, { method: "PATCH", token, body: changes });
}

export function setIntegrationEnabled(token, id, enabled) {
  return updateIntegration(token, id, { enabled });
}

// Gives the integration a new public_id. The old link stops working at once.
export function rotateIntegrationLink(token, id) {
  return apiFetch(`/integrations/${id}/rotate`, { method: "POST", token });
}
