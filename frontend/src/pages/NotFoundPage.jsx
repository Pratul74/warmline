// Any URL that matches no route.
import { Link } from "react-router";
import { CenteredMessage } from "@/components/layout/CenteredMessage";
import { Button } from "@/components/ui/button";

export default function NotFoundPage() {
  return (
    <CenteredMessage
      eyebrow="404"
      title="This page doesn't exist"
      actions={
        <Button asChild>
          <Link to="/">Go to the home page</Link>
        </Button>
      }
    >
      <title>Page not found · Warmline</title>
      <p>Check the address, or start again from the home page.</p>
    </CenteredMessage>
  );
}
