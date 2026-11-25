import styles from "./UploadResult.module.css";

// Shows the outcome of one upload: the counts, or the server's error exactly as
// it was sent (its message, plus a table of row errors for a 422).
export default function UploadResult({ result, error }) {
  if (result) {
    return (
      <div className={styles.success} role="status">
        <strong>Upload saved.</strong> {result.inserted} added, {result.updated} updated,{" "}
        {result.unchanged} unchanged.
      </div>
    );
  }
  if (!error) return null;

  return (
    <div className={styles.failure} role="alert">
      <p className={styles.message}>{error.message}</p>
      {error.errors.length > 0 && (
        <table className={styles.table}>
          <thead>
            <tr>
              <th>Row</th>
              <th>Column</th>
              <th>Problem</th>
            </tr>
          </thead>
          <tbody>
            {error.errors.map((item, index) => (
              <tr key={index}>
                <td>{item.row ?? "–"}</td>
                <td>{item.field ?? "–"}</td>
                <td>{item.message}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
