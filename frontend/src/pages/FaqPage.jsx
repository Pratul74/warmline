import { useState } from "react";
import { useAuth } from "../auth/AuthContext.jsx";
import FaqList from "../components/FaqList.jsx";
import FaqUploadForm from "../components/FaqUploadForm.jsx";
import OwnerHeader from "../components/OwnerHeader.jsx";
import styles from "./FaqPage.module.css";

export default function FaqPage() {
  const { token } = useAuth();
  // Bumped after each successful upload so the list reloads.
  const [refreshKey, setRefreshKey] = useState(0);

  return (
    <div className={styles.page}>
      <OwnerHeader />

      <section className="card">
        <h2 className={styles.sectionTitle}>Upload FAQ entries</h2>
        <FaqUploadForm token={token} onUploaded={() => setRefreshKey((n) => n + 1)} />
      </section>

      <section>
        <h2 className={styles.sectionTitle}>Your FAQ entries</h2>
        <FaqList token={token} refreshKey={refreshKey} />
      </section>
    </div>
  );
}
