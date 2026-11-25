import { useState } from "react";
import { MAX_GREETING_LENGTH, MAX_NAME_LENGTH, createIntegration } from "../api/integrations.js";
import ErrorBanner from "./ErrorBanner.jsx";
import styles from "./IntegrationForm.module.css";

export default function CreateIntegrationForm({ token, onCreated }) {
  const [name, setName] = useState("");
  const [greeting, setGreeting] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  async function handleSubmit(event) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const created = await createIntegration(token, { name: name.trim(), greeting: greeting.trim() });
      onCreated(created);
      setName("");
      setGreeting("");
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <form className={styles.form} onSubmit={handleSubmit}>
      <ErrorBanner message={error} />
      <label>
        Name
        <input
          required
          maxLength={MAX_NAME_LENGTH}
          placeholder="Website chat"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
      </label>
      <label>
        Greeting (optional)
        <textarea
          rows={2}
          maxLength={MAX_GREETING_LENGTH}
          placeholder="Hi! How can we help you today?"
          value={greeting}
          onChange={(e) => setGreeting(e.target.value)}
        />
      </label>
      <div>
        <button type="submit" disabled={saving || !name.trim()}>
          {saving ? "Creating…" : "Create integration"}
        </button>
      </div>
    </form>
  );
}
