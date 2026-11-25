import { useState } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router";
import { useAuth } from "../auth/AuthContext.jsx";
import ErrorBanner from "../components/ErrorBanner.jsx";
import styles from "./AuthForm.module.css";

export default function LoginPage() {
  const { account, login, notice } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();


  const from = location.state?.from || "/";
  const registeredEmail = location.state?.registeredEmail;

  const [email, setEmail] = useState(registeredEmail || "");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  if (account) return <Navigate to={from} replace />;

  async function handleSubmit(event) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await login(email.trim(), password);
      navigate(from, { replace: true });
    } catch (err) {
      setError(err.message);
      setSubmitting(false);
    }
  }

  return (
    <main className="page-center">
      <form className={`card ${styles.form}`} onSubmit={handleSubmit}>
        <h1>Log in to Warmline</h1>
        {registeredEmail && !error && (
          <p className={styles.success}>Account created. Please log in.</p>
        )}
        {notice && !error && <p className={styles.notice}>{notice}</p>}
        <ErrorBanner message={error} />

        <label>
          Email
          <input
            type="email"
            autoComplete="email"
            required
            maxLength={320}
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </label>
        <label>
          Password
          <input
            type="password"
            autoComplete="current-password"
            required
            maxLength={128}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </label>
        <button type="submit" disabled={submitting}>
          {submitting ? "Logging in…" : "Log in"}
        </button>
        <p className="muted">
          No account yet? <Link to="/register">Create one</Link>
        </p>
      </form>
    </main>
  );
}
