import { apiFetch } from "./client.js";

export const MAX_NAME_LENGTH = 100;
export const MAX_GREETING_LENGTH = 500;


export function listIntegrations(token) {
  return apiFetch("/integrations", { token });
}

export function createIntegration(token, { name, greeting }) {
  return apiFetch("/integrations", {
    method: "POST",
    token,
    body: { name, greeting: greeting || null },
  });
}

export function updateIntegration(token, id, changes) {
  return apiFetch(`/integrations/${id}`, { method: "PATCH", token, body: changes });
}

export function setIntegrationEnabled(token, id, enabled) {
  return updateIntegration(token, id, { enabled });
}

export function rotateIntegrationLink(token, id) {
  return apiFetch(`/integrations/${id}/rotate`, { method: "POST", token });
}
