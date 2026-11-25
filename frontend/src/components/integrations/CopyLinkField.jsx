// The chat link in a read-only box, with Copy and Open buttons. The "Copied" state is also
// announced to screen readers through a polite live region.
import { Check, Copy, ExternalLink } from "lucide-react";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export function CopyLinkField({ url, label }) {
  const [status, setStatus] = useState(null); // null | "copied" | "failed"

  // The "Copied" label goes back to "Copy" after two seconds.
  useEffect(() => {
    if (status !== "copied") return;
    const timer = setTimeout(() => setStatus(null), 2000);
    return () => clearTimeout(timer);
  }, [status]);

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(url);
      setStatus("copied");
    } catch {
      // The clipboard is refused on plain http (except localhost) or by browser settings.
      setStatus("failed");
    }
  }

  return (
    <div className="grid gap-1.5">
      <div className="flex gap-2">
        <Input
          readOnly
          value={url}
          aria-label={label}
          onFocus={(event) => event.target.select()}
          className="bg-muted font-mono text-xs md:text-xs"
        />
        <Button type="button" variant="outline" onClick={handleCopy} className="w-24">
          {status === "copied" ? <Check aria-hidden="true" /> : <Copy aria-hidden="true" />}
          {status === "copied" ? "Copied" : "Copy"}
        </Button>
        <Button variant="outline" size="icon" asChild>
          <a href={url} target="_blank" rel="noreferrer">
            <ExternalLink aria-hidden="true" />
            <span className="sr-only">Open the chat in a new tab</span>
          </a>
        </Button>
      </div>
      <p aria-live="polite" className="text-xs text-destructive">
        {status === "failed" && "Couldn't copy. Select the link and copy it by hand."}
        <span className="sr-only">{status === "copied" && "Link copied"}</span>
      </p>
    </div>
  );
}
