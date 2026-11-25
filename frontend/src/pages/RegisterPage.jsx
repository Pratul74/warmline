// /register. Creates an owner account, then sends the owner to /login with the email filled in.
// Browser checks (required, length) are hints; the server's rules are the ones that count and
// its message is shown as it is.
import { useState } from "react";
import { Link, Navigate, useNavigate } from "react-router";
import {
  MAX_BUSINESS_NAME_LENGTH,
  MAX_PASSWORD_LENGTH,
  MIN_PASSWORD_LENGTH,
  register,
} from "@/api/auth";
import { useAuth } from "@/auth/AuthContext";
import { ErrorMessage } from "@/components/feedback/ErrorMessage";
import { AuthLayout } from "@/components/layout/AuthLayout";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { useSubmit } from "@/hooks/useSubmit";

export default function RegisterPage() {
  const { account } = useAuth();
  const navigate = useNavigate();

  const [businessName, setBusinessName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const { submit, submitting, error } = useSubmit(() =>
    register({ email: email.trim(), password, businessName: businessName.trim() }),
  );

  if (account) return <Navigate to="/app/integrations" replace />;

  async function handleSubmit(event) {
    event.preventDefault();
    const { ok, result } = await submit();
    if (ok) navigate("/login", { state: { registeredEmail: result.email } });
  }

  return (
    <AuthLayout title="Create your account" subtitle="Set up your business in under a minute.">
      <title>Create account · Warmline</title>
      <form className="grid gap-5" onSubmit={handleSubmit}>
        <ErrorMessage error={error} />
        <Field label="Business name" hint="Customers see this name in the chat.">
          {(props) => (
            <Input
              {...props}
              autoComplete="organization"
              required
              maxLength={MAX_BUSINESS_NAME_LENGTH}
              value={businessName}
              onChange={(event) => setBusinessName(event.target.value)}
            />
          )}
        </Field>
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
        <Field label="Password" hint={`At least ${MIN_PASSWORD_LENGTH} characters.`}>
          {(props) => (
            <Input
              {...props}
              type="password"
              autoComplete="new-password"
              required
              minLength={MIN_PASSWORD_LENGTH}
              maxLength={MAX_PASSWORD_LENGTH}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          )}
        </Field>
        <Button type="submit" disabled={submitting}>
          {submitting ? "Creating account…" : "Create account"}
        </Button>
        <p className="text-sm text-muted-foreground">
          Already have an account?{" "}
          <Link to="/login" className="font-medium text-primary underline-offset-4 hover:underline">
            Log in
          </Link>
        </p>
      </form>
    </AuthLayout>
  );
}
