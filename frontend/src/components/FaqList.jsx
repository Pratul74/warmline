import { useEffect, useState } from "react";
import { listFaqEntries } from "../api/faq.js";
import ErrorBanner from "./ErrorBanner.jsx";
import Spinner from "./Spinner.jsx";
import styles from "./FaqList.module.css";

const PAGE_SIZE = 10;


export default function FaqList({ token, refreshKey }) {
  const [page, setPage] = useState(1);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    listFaqEntries(token, page, PAGE_SIZE)
      .then((result) => {
        if (!cancelled) setData(result);
      })
      .catch((err) => {
        if (!cancelled) setError(err.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [token, page, refreshKey, attempt]);

  if (loading && !data) return <Spinner label="Loading FAQ entries…" />;
  if (error) return <ErrorBanner message={error} onRetry={() => setAttempt((n) => n + 1)} />;
  if (data.total === 0) {
    return (
      <div className={`card ${styles.empty}`}>
        <p>No FAQ entries yet.</p>
        <p className="muted">Upload a CSV above, or start from the sample template.</p>
      </div>
    );
  }

  const pages = Math.max(1, Math.ceil(data.total / PAGE_SIZE));
  return (
    <div className={styles.wrapper}>
      <table className={styles.table}>
        <thead>
          <tr>
            <th>Question</th>
            <th>Answer</th>
            <th>Last changed</th>
          </tr>
        </thead>
        <tbody>
          {data.items.map((entry) => (
            <tr key={entry.id}>
              <td>{entry.question}</td>
              <td>{entry.answer}</td>
              <td className={styles.date}>{new Date(entry.updated_at).toLocaleString()}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className={styles.pager}>
        <button
          type="button"
          className="secondary"
          disabled={page <= 1 || loading}
          onClick={() => setPage((p) => p - 1)}
        >
          Previous
        </button>
        <span>
          Page {data.page} of {pages} · {data.total} entries {loading && "· loading…"}
        </span>
        <button
          type="button"
          className="secondary"
          disabled={page >= pages || loading}
          onClick={() => setPage((p) => p + 1)}
        >
          Next
        </button>
      </div>
    </div>
  );
}
