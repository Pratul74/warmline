// /app/integrations: the owner's chat links. Shows a skeleton while loading, an error with
// "Try again", an empty state with the first step, or the list of cards.
import { Link2, Plus } from "lucide-react";
import { useCallback, useState } from "react";
import { createIntegration, listIntegrations } from "@/api/integrations";
import { useAuth } from "@/auth/AuthContext";
import { EmptyState } from "@/components/feedback/EmptyState";
import { ErrorMessage } from "@/components/feedback/ErrorMessage";
import { useToast } from "@/components/feedback/Toaster";
import { IntegrationCard } from "@/components/integrations/IntegrationCard";
import { IntegrationFormDialog } from "@/components/integrations/IntegrationFormDialog";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useApiRequest } from "@/hooks/useApiRequest";

function ListSkeleton() {
  return (
    <div aria-busy="true" className="grid gap-4">
      <p role="status" className="sr-only">
        Loading chat links…
      </p>
      {[0, 1].map((key) => (
        <Skeleton key={key} className="h-52 w-full rounded-lg" />
      ))}
    </div>
  );
}

export default function IntegrationsPage() {
  const { token } = useAuth();
  const toast = useToast();
  const [creating, setCreating] = useState(false);
  const load = useCallback(() => listIntegrations(token), [token]);
  const { data: integrations, loading, error, reload, setData } = useApiRequest(load);

  function handleCreated(created) {
    setData((current) => [...(current ?? []), created]);
    toast({
      title: "Chat link created",
      description: "Copy it and put it behind a Chat button.",
      variant: "success",
    });
  }

  // A card sends back the integration as the API returned it after a change.
  function handleChanged(updated) {
    setData((current) => current.map((item) => (item.id === updated.id ? updated : item)));
  }

  const newButton = (
    <Button onClick={() => setCreating(true)}>
      <Plus aria-hidden="true" /> New chat link
    </Button>
  );

  return (
    <>
      <PageHeader
        title="Chat links"
        description="Each link opens your assistant for customers. Put it behind a “Chat” button on your website, app or social profile."
        actions={integrations?.length > 0 && newButton}
      />

      {loading && !integrations && <ListSkeleton />}
      {error && <ErrorMessage error={error} onRetry={reload} />}
      {!loading && !error && integrations?.length === 0 && (
        <EmptyState icon={Link2} title="No chat links yet" action={newButton}>
          Create your first link, then share it with customers. You can disable or replace it any
          time.
        </EmptyState>
      )}
      {integrations?.length > 0 && (
        <ul className="grid gap-4" aria-label="Your chat links">
          {integrations.map((integration) => (
            <IntegrationCard
              key={integration.id}
              token={token}
              integration={integration}
              onChanged={handleChanged}
            />
          ))}
        </ul>
      )}

      <IntegrationFormDialog
        open={creating}
        onOpenChange={setCreating}
        title="New chat link"
        description="You get a unique link you can share right away."
        submitLabel="Create link"
        onSave={(values) => createIntegration(token, values)}
        onSaved={handleCreated}
      />
    </>
  );
}
