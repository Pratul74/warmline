import { useRef, useState } from "react";
import { MAX_UPLOAD_BYTES, TEMPLATE_URL, uploadFaqCsv } from "../api/faq.js";
import UploadResult from "./UploadResult.jsx";
import styles from "./FaqUploadForm.module.css";

function checkFile(file) {
  if (!file.name.toLowerCase().endsWith(".csv")) return "Choose a .csv file.";
  if (file.size > MAX_UPLOAD_BYTES) return "The file is larger than 1 MB.";
  if (file.size === 0) return "The file is empty.";
  return null;
}

export default function FaqUploadForm({ token, onUploaded }) {
  const inputRef = useRef(null);
  const [file, setFile] = useState(null);
  const [checkError, setCheckError] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  function handleChoose(event) {
    const chosen = event.target.files[0] ?? null;
    setFile(chosen);
    setResult(null);
    setError(null);
    setCheckError(chosen ? checkFile(chosen) : null);
  }

  async function handleSubmit(event) {
    event.preventDefault();
    if (!file || checkError) return;
    setUploading(true);
    setResult(null);
    setError(null);
    try {
      const counts = await uploadFaqCsv(token, file);
      setResult(counts);
      setFile(null);
      inputRef.current.value = "";
      onUploaded(counts);
    } catch (err) {
      setError(err);
    } finally {
      setUploading(false);
    }
  }

  return (
    <form className={styles.form} onSubmit={handleSubmit}>
      <label>
        CSV file with the columns question and answer
        <input ref={inputRef} type="file" accept=".csv,text/csv" onChange={handleChoose} />
      </label>
      {checkError && (
        <p className={styles.checkError} role="alert">
          {checkError}
        </p>
      )}
      <div className={styles.actions}>
        <button type="submit" disabled={!file || Boolean(checkError) || uploading}>
          {uploading ? "Uploading…" : "Upload"}
        </button>
        <a href={TEMPLATE_URL} download>
          Download sample template
        </a>
      </div>
      <p className="muted">
        Up to 500 rows and 1 MB. Questions you already have get the new answer; nothing is
        deleted. If any row has a problem, nothing is saved.
      </p>
      <UploadResult result={result} error={error} />
    </form>
  );
}
