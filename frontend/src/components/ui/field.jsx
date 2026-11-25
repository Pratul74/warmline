// A form field: label, the input itself, an optional hint and an optional error, wired
// together with ids so screen readers read the label, hint and error with the input.
//
//   <Field label="Email" hint="We never share it." error={fieldError}>
//     {(props) => <Input type="email" {...props} />}
//   </Field>
import { useId } from "react";
import { Label } from "./label";

export function Field({ label, hint, error, children }) {
  const id = useId();
  const hintId = hint ? `${id}-hint` : undefined;
  const errorId = error ? `${id}-error` : undefined;
  const describedBy = [hintId, errorId].filter(Boolean).join(" ") || undefined;

  return (
    <div className="grid gap-2">
      <Label htmlFor={id}>{label}</Label>
      {children({ id, "aria-describedby": describedBy, "aria-invalid": error ? true : undefined })}
      {hint && (
        <p id={hintId} className="text-xs text-muted-foreground">
          {hint}
        </p>
      )}
      {error && (
        <p id={errorId} className="text-xs text-destructive">
          {error}
        </p>
      )}
    </div>
  );
}
