import { useState } from "react";
import { Link, Navigate, useNavigate } from "react-router";
import {
  MAX_BUSINESS_NAME_LENGTH,
  MAX_PASSWORD_LENGTH,
  MIN_PASSWORD_LENGTH,
  register,
} from "../api/auth.js";
import { useAuth } from "../auth/AuthContext.jsx";
import ErrorBanner from "../components/ErrorBanner.jsx";
import styles from "./AuthForm.module.css";

export default function RegisterPage() {
  const { account } = useAuth();
  const navigate = useNavigate();

  const [businessName, setBusinessName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  if (account) return <Navigate to="/" replace />;

  async function handleSubmit(event) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const created = await register({
        email: email.trim(),
        password,
        businessName: businessName.trim(),
      });
      navigate("/login", { state: { registeredEmail: created.email } });
    } catch (err) {
      setError(err.message);
      setSubmitting(false);
    }
  }

  return (
    <main className="page-center">
      <form className={`card ${styles.form}`} onSubmit={handleSubmit}>
        <h1>Create your account</h1>
        <ErrorBanner message={error} />

        <label>
          Business name
          <input
            required
            maxLength={MAX_BUSINESS_NAME_LENGTH}
            value={businessName}
            onChange={(e) => setBusinessName(e.target.value)}
          />
        </label>
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
            autoComplete="new-password"
            required
            minLength={MIN_PASSWORD_LENGTH}
            maxLength={MAX_PASSWORD_LENGTH}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          <span className="muted">At least {MIN_PASSWORD_LENGTH} characters.</span>
        </label>
        <button type="submit" disabled={submitting}>
          {submitting ? "Creating account…" : "Create account"}
        </button>
        <p className="muted">
          Already have an account? <Link to="/login">Log in</Link>
        </p>
      </form>
    </main>
  );
}
