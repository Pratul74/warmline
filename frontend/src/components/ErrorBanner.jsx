import styles from "./ErrorBanner.module.css";

export default function ErrorBanner({ message, onRetry }) {
  if (!message) return null;
  return (
    <div className={styles.banner} role="alert">
      <span>{message}</span>
      {onRetry && (
        <button type="button" className="secondary" onClick={onRetry}>
          Retry
        </button>
      )}
    </div>
  );
}
