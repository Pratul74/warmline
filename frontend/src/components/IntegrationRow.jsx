import { useState } from "react";
import {
  MAX_GREETING_LENGTH,
  MAX_NAME_LENGTH,
  rotateIntegrationLink,
  setIntegrationEnabled,
  updateIntegration,
} from "../api/integrations.js";
import ErrorBanner from "./ErrorBanner.jsx";
import styles from "./IntegrationRow.module.css";
import formStyles from "./IntegrationForm.module.css";

const ROTATE_WARNING =
  "Get a new link for this integration?\n\n" +
  "The current link stops working immediately. You will need to update it everywhere you placed it.";

function formatDate(value) {
  return new Date(value).toLocaleString();
}

export default function IntegrationRow({ token, integration, onChanged }) {
  const [busy, setBusy] = useState(null);
  const [error, setError] = useState(null);
  const [copied, setCopied] = useState(false);
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(integration.name);
  const [greeting, setGreeting] = useState(integration.greeting || "");

  const active = integration.status === "active";

  // Runs one API change; shows its error in this row only.
  async function run(kind, request) {
    setBusy(kind);
    setError(null);
    try {
      onChanged(await request());
      return true;
    } catch (err) {
      setError(err.message);
      return false;
    } finally {
      setBusy(null);
    }
  }

  function handleToggle() {
    run("toggle", () => setIntegrationEnabled(token, integration.id, !active));
  }

  function handleRotate() {
    if (!window.confirm(ROTATE_WARNING)) return;
    run("rotate", () => rotateIntegrationLink(token, integration.id));
  }

  function startEditing() {
    setName(integration.name);
    setGreeting(integration.greeting || "");
    setError(null);
    setEditing(true);
  }

  async function handleSave(event) {
    event.preventDefault();
    const saved = await run("save", () =>
      updateIntegration(token, integration.id, { name: name.trim(), greeting: greeting.trim() }),
    );
    if (saved) setEditing(false);
  }

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(integration.embed_url);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setError("Could not copy. Select the link and copy it by hand.");
    }
  }

  return (
    <li className={`card ${styles.row}`}>
      <div className={styles.top}>
        <h3>{integration.name}</h3>
        <span className={active ? styles.badgeActive : styles.badgeDisabled}>
          {active ? "Active" : "Disabled"}
        </span>
      </div>

      <ErrorBanner message={error} />

      {editing ? (
        <form className={formStyles.form} onSubmit={handleSave}>
          <label>
            Name
            <input
              required
              maxLength={MAX_NAME_LENGTH}
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </label>
          <label>
            Greeting (leave empty for none)
            <textarea
              rows={2}
              maxLength={MAX_GREETING_LENGTH}
              value={greeting}
              onChange={(e) => setGreeting(e.target.value)}
            />
          </label>
          <div className={styles.actions}>
            <button type="submit" disabled={busy !== null || !name.trim()}>
              {busy === "save" ? "Saving…" : "Save"}
            </button>
            <button
              type="button"
              className="secondary"
              disabled={busy !== null}
              onClick={() => setEditing(false)}
            >
              Cancel
            </button>
          </div>
        </form>
      ) : (
        <p className={integration.greeting ? undefined : "muted"}>
          {integration.greeting || "No greeting set."}
        </p>
      )}

      <div className={styles.link}>
        <input readOnly value={integration.embed_url} aria-label="Chat link" onFocus={(e) => e.target.select()} />
        <button type="button" className="secondary" onClick={handleCopy}>
          {copied ? "Copied!" : "Copy"}
        </button>
        <a href={integration.embed_url} target="_blank" rel="noreferrer">
          Open
        </a>
      </div>

      <p className={`muted ${styles.meta}`}>
        Created {formatDate(integration.created_at)}
        {integration.disabled_at && ` · Disabled ${formatDate(integration.disabled_at)}`}
      </p>

      {!editing && (
        <div className={styles.actions}>
          <button type="button" className="secondary" disabled={busy !== null} onClick={startEditing}>
            Edit
          </button>
          <button
            type="button"
            className={active ? "danger" : undefined}
            disabled={busy !== null}
            onClick={handleToggle}
          >
            {busy === "toggle" ? (active ? "Disabling…" : "Enabling…") : active ? "Disable" : "Enable"}
          </button>
          <button type="button" className="secondary" disabled={busy !== null} onClick={handleRotate}>
            {busy === "rotate" ? "Rotating…" : "Rotate link"}
          </button>
        </div>
      )}
    </li>
  );
}
