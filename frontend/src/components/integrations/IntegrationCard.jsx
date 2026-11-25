// One chat link: its name, status, greeting, the link itself, and the actions
// (edit, disable or enable, rotate). Each change reports the updated integration to the page
// through onChanged and confirms with a toast; errors stay in the card.
import { Pencil, Power, RefreshCw } from "lucide-react";
import { useState } from "react";
import {
  rotateIntegrationLink,
  setIntegrationEnabled,
  updateIntegration,
} from "@/api/integrations";
import { ErrorMessage } from "@/components/feedback/ErrorMessage";
import { useToast } from "@/components/feedback/Toaster";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardHeader, CardTitle } from "@/components/ui/card";
import { useSubmit } from "@/hooks/useSubmit";
import { formatDateTime } from "@/utils/formatDate";
import { CopyLinkField } from "./CopyLinkField";
import { IntegrationFormDialog } from "./IntegrationFormDialog";
import { RotateLinkDialog } from "./RotateLinkDialog";

export function IntegrationCard({ token, integration, onChanged }) {
  const toast = useToast();
  const [dialog, setDialog] = useState(null); // null | "edit" | "rotate"
  const active = integration.status === "active";
  const toggle = useSubmit(() => setIntegrationEnabled(token, integration.id, !active));

  async function handleToggle() {
    const { ok, result } = await toggle.submit();
    if (!ok) return;
    onChanged(result);
    toast(
      active
        ? {
            title: "Chat link disabled",
            description: "Customers can't chat on it until you enable it again.",
          }
        : {
            title: "Chat link enabled",
            description: "Customers can chat on it again.",
            variant: "success",
          },
    );
  }

  return (
    <Card as="li">
      <CardHeader className="flex-row flex-wrap items-center justify-between gap-2">
        <CardTitle as="h3">{integration.name}</CardTitle>
        <Badge variant={active ? "success" : "muted"}>
          <span className="size-1.5 rounded-full bg-current" aria-hidden="true" />
          {active ? "Active" : "Disabled"}
        </Badge>
      </CardHeader>

      <p className={integration.greeting ? "text-sm" : "text-sm text-muted-foreground italic"}>
        {integration.greeting ? `“${integration.greeting}”` : "No greeting set."}
      </p>

      <CopyLinkField url={integration.embed_url} label={`Chat link for ${integration.name}`} />
      <ErrorMessage error={toggle.error} />

      <div className="flex flex-wrap items-center justify-between gap-3 border-t pt-4">
        <p className="text-xs text-muted-foreground">
          Created {formatDateTime(integration.created_at)}
          {integration.disabled_at && ` · Disabled ${formatDateTime(integration.disabled_at)}`}
        </p>
        <div className="flex flex-wrap gap-2">
          <Button variant="ghost" size="sm" onClick={() => setDialog("edit")}>
            <Pencil aria-hidden="true" /> Edit
          </Button>
          <Button variant="ghost" size="sm" onClick={handleToggle} disabled={toggle.submitting}>
            <Power aria-hidden="true" />
            {toggle.submitting ? "Saving…" : active ? "Disable" : "Enable"}
          </Button>
          <Button variant="ghost" size="sm" onClick={() => setDialog("rotate")}>
            <RefreshCw aria-hidden="true" /> Rotate link
          </Button>
        </div>
      </div>

      <IntegrationFormDialog
        open={dialog === "edit"}
        onOpenChange={(open) => setDialog(open ? "edit" : null)}
        title="Edit chat link"
        initial={integration}
        submitLabel="Save changes"
        onSave={(values) => updateIntegration(token, integration.id, values)}
        onSaved={(updated) => {
          onChanged(updated);
          toast({ title: "Changes saved", variant: "success" });
        }}
      />
      <RotateLinkDialog
        open={dialog === "rotate"}
        onOpenChange={(open) => setDialog(open ? "rotate" : null)}
        integrationName={integration.name}
        onRotate={() => rotateIntegrationLink(token, integration.id)}
        onRotated={(updated) => {
          onChanged(updated);
          toast({
            title: "New link ready",
            description: "The old link no longer works.",
            variant: "success",
          });
        }}
      />
    </Card>
  );
}
