// Shown by the ErrorBoundary when something crashed while drawing a page. It uses plain <a>
// links, not the router, because the router itself may be what broke. Reloading also fixes
// the common case of a page file that no longer exists after a new version was deployed.
import { CenteredMessage } from "@/components/layout/CenteredMessage";
import { Button } from "@/components/ui/button";

export default function ErrorPage() {
  return (
    <CenteredMessage
      eyebrow="Something went wrong"
      title="This page couldn't load"
      actions={
        <>
          <Button onClick={() => window.location.reload()}>Reload the page</Button>
          <Button variant="outline" asChild>
            <a href="/">Go to the home page</a>
          </Button>
        </>
      }
    >
      <title>Error · Warmline</title>
      <p>The problem has been logged. Reloading usually fixes it.</p>
    </CenteredMessage>
  );
}
