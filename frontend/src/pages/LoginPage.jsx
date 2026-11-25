// /login. After logging in, the owner goes back to the page they were trying to open
// (RequireAuth remembered it), or to their integrations.
import { useState } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router";
import { useAuth } from "@/auth/AuthContext";
import { ErrorMessage } from "@/components/feedback/ErrorMessage";
import { AuthLayout } from "@/components/layout/AuthLayout";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { useSubmit } from "@/hooks/useSubmit";

export default function LoginPage() {
  const { account, login, notice } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const from = location.state?.from || "/app/integrations";
  const registeredEmail = location.state?.registeredEmail;

  const [email, setEmail] = useState(registeredEmail || "");
  const [password, setPassword] = useState("");
  const { submit, submitting, error } = useSubmit(() => login(email.trim(), password));

  if (account) return <Navigate to={from} replace />;

  async function handleSubmit(event) {
    event.preventDefault();
    const { ok } = await submit();
    if (ok) navigate(from, { replace: true });
  }

  return (
    <AuthLayout title="Log in" subtitle="Welcome back. Manage your chat links and FAQ.">
      <title>Log in · Warmline</title>
      <form className="grid gap-5" onSubmit={handleSubmit}>
        {registeredEmail && !error && (
          <p role="status" className="rounded-md bg-success-soft p-3 text-sm text-success">
            Account created. Please log in.
          </p>
        )}
        {notice && !error && (
          <p role="status" className="rounded-md bg-primary-soft p-3 text-sm text-primary-hover">
            {notice}
          </p>
        )}
        <ErrorMessage error={error} />

        <Field label="Email">
          {(props) => (
            <Input
              {...props}
              type="email"
              autoComplete="email"
              required
              maxLength={320}
              value={email}
              onChange={(event) => setEmail(event.target.value)}
            />
          )}
        </Field>
        <Field label="Password">
          {(props) => (
            <Input
              {...props}
              type="password"
              autoComplete="current-password"
              required
              maxLength={128}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          )}
        </Field>
        <Button type="submit" disabled={submitting}>
          {submitting ? "Logging in…" : "Log in"}
        </Button>
        <p className="text-sm text-muted-foreground">
          No account yet?{" "}
          <Link
            to="/register"
            className="font-medium text-primary underline-offset-4 hover:underline"
          >
            Create one
          </Link>
        </p>
      </form>
    </AuthLayout>
  );
}
