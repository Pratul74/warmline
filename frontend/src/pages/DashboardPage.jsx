import { useEffect, useState } from "react";
import { listIntegrations } from "../api/integrations.js";
import { useAuth } from "../auth/AuthContext.jsx";
import CreateIntegrationForm from "../components/CreateIntegrationForm.jsx";
import ErrorBanner from "../components/ErrorBanner.jsx";
import IntegrationRow from "../components/IntegrationRow.jsx";
import OwnerHeader from "../components/OwnerHeader.jsx";
import Spinner from "../components/Spinner.jsx";
import styles from "./DashboardPage.module.css";

export default function DashboardPage() {
  const { token } = useAuth();

  const [integrations, setIntegrations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(null);
  const [loadAttempt, setLoadAttempt] = useState(0); // bump to retry

  useEffect(() => {
    let cancelled = false; // ignore the answer if the page went away meanwhile
    setLoading(true);
    setLoadError(null);
    listIntegrations(token)
      .then((list) => {
        if (!cancelled) setIntegrations(list);
      })
      .catch((error) => {
        if (!cancelled) setLoadError(error.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [token, loadAttempt]);

  function handleCreated(integration) {
    setIntegrations((current) => [...current, integration]);
  }

  // Each row sends back the integration as the API returned it after a change.
  function handleChanged(updated) {
    setIntegrations((current) => current.map((item) => (item.id === updated.id ? updated : item)));
  }

  return (
    <div className={styles.page}>
      <OwnerHeader />

      <section className="card">
        <h2 className={styles.sectionTitle}>New integration</h2>
        <p className="muted">
          Each integration gets its own chat link. Put the link behind a "Chat" button on your
          website or app.
        </p>
        <CreateIntegrationForm token={token} onCreated={handleCreated} />
      </section>

      <section>
        <h2 className={styles.sectionTitle}>Your integrations</h2>
        {loading && <Spinner label="Loading integrations…" />}
        {!loading && loadError && (
          <ErrorBanner message={loadError} onRetry={() => setLoadAttempt((n) => n + 1)} />
        )}
        {!loading && !loadError && integrations.length === 0 && (
          <div className={`card ${styles.empty}`}>
            <p>No integrations yet.</p>
            <p className="muted">Create one above to get your first chat link.</p>
          </div>
        )}
        {!loading && !loadError && integrations.length > 0 && (
          <ul className={styles.list}>
            {integrations.map((integration) => (
              <IntegrationRow
                key={integration.id}
                token={token}
                integration={integration}
                onChanged={handleChanged}
              />
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
