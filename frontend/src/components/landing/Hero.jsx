// The first screen of the landing page: what Warmline is, for whom, and the two next steps.
// Text on the left, the chat picture on the right (below the text on phones).
import { ArrowRight } from "lucide-react";
import { Link } from "react-router";
import { Button } from "@/components/ui/button";
import { ProductMockup } from "./ProductMockup";

export function Hero() {
  return (
    <section className="mx-auto grid max-w-6xl items-center gap-14 overflow-x-clip px-6 pt-10 pb-20 lg:grid-cols-[1.15fr_1fr] lg:pt-16">
      <div>
        <p className="text-sm font-semibold tracking-wide text-primary uppercase">
          Sales and support assistant for small businesses
        </p>
        <h1 className="mt-4 text-4xl leading-[1.1] font-semibold text-balance sm:text-5xl lg:text-6xl">
          Answer every customer, even when you're busy with the last one.
        </h1>
        <p className="mt-6 max-w-xl text-lg text-pretty text-muted-foreground">
          Warmline answers questions from your own FAQ, takes down leads and books appointments, and
          it always checks with the customer before it saves anything.
        </p>
        <div className="mt-8 flex flex-wrap gap-3">
          <Button size="lg" asChild>
            <Link to="/register">
              Create your assistant <ArrowRight aria-hidden="true" />
            </Link>
          </Button>
          <Button size="lg" variant="outline" asChild>
            <a href="#how-it-works">See how it works</a>
          </Button>
        </div>
      </div>
      <ProductMockup />
    </section>
  );
}
