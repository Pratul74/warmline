// The closing call to action. No pricing: the project has none, so none is shown.
import { Link } from "react-router";
import { Button } from "@/components/ui/button";

export function CallToAction() {
  return (
    <section className="mx-auto max-w-6xl px-6 py-20">
      <div className="rounded-2xl border bg-primary-soft px-8 py-14 text-center">
        <h2 className="text-3xl font-semibold sm:text-4xl">Ready for your first chat link?</h2>
        <p className="mx-auto mt-3 max-w-lg text-muted-foreground">
          Create an account, upload your FAQ and share the link. It takes a few minutes.
        </p>
        <Button size="lg" className="mt-8" asChild>
          <Link to="/register">Get started</Link>
        </Button>
      </div>
    </section>
  );
}
