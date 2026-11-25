// One dialog for both "New chat link" and "Edit": a name and an optional greeting.
// `onSave(values)` must return the API promise; the dialog closes only when it succeeds and
// shows the server's error otherwise.
import { useState } from "react";
import { MAX_GREETING_LENGTH, MAX_NAME_LENGTH } from "@/api/integrations";
import { ErrorMessage } from "@/components/feedback/ErrorMessage";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { useSubmit } from "@/hooks/useSubmit";

// The form is its own component so its fields start fresh every time the dialog opens
// (Radix removes the dialog's content from the page while it is closed).
function IntegrationForm({ initial, submitLabel, onSave, onDone }) {
  const [name, setName] = useState(initial?.name ?? "");
  const [greeting, setGreeting] = useState(initial?.greeting ?? "");
  const { submit, submitting, error } = useSubmit(onSave);

  async function handleSubmit(event) {
    event.preventDefault();
    const { ok, result } = await submit({ name: name.trim(), greeting: greeting.trim() });
    if (ok) onDone(result);
  }

  return (
    <form className="grid gap-5" onSubmit={handleSubmit}>
      <ErrorMessage error={error} />
      <Field label="Name" hint="Only you see this, e.g. “Website chat” or “Instagram bio”.">
        {(props) => (
          <Input
            {...props}
            required
            maxLength={MAX_NAME_LENGTH}
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
        )}
      </Field>
      <Field
        label="Greeting (optional)"
        hint="The first message customers see. Leave empty for none."
      >
        {(props) => (
          <Textarea
            {...props}
            rows={3}
            maxLength={MAX_GREETING_LENGTH}
            placeholder="Hi! How can we help you today?"
            value={greeting}
            onChange={(event) => setGreeting(event.target.value)}
          />
        )}
      </Field>
      <DialogFooter>
        <DialogClose asChild>
          <Button type="button" variant="outline">
            Cancel
          </Button>
        </DialogClose>
        <Button type="submit" disabled={submitting || !name.trim()}>
          {submitting ? "Saving…" : submitLabel}
        </Button>
      </DialogFooter>
    </form>
  );
}

export function IntegrationFormDialog({
  open,
  onOpenChange,
  title,
  description,
  initial,
  submitLabel,
  onSave,
  onSaved,
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          {description && <DialogDescription>{description}</DialogDescription>}
        </DialogHeader>
        <IntegrationForm
          initial={initial}
          submitLabel={submitLabel}
          onSave={onSave}
          onDone={(result) => {
            onSaved(result);
            onOpenChange(false);
          }}
        />
      </DialogContent>
    </Dialog>
  );
}
