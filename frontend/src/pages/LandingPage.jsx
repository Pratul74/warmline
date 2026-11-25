// /: the public landing page. Every claim on it is a feature that exists today: no
// testimonials, logos, numbers or prices that we could not back up.
import { CallToAction } from "@/components/landing/CallToAction";
import { Features } from "@/components/landing/Features";
import { Hero } from "@/components/landing/Hero";
import { HowItWorks } from "@/components/landing/HowItWorks";
import { Safety } from "@/components/landing/Safety";
import { Footer } from "@/components/layout/Footer";
import { PublicHeader } from "@/components/layout/PublicHeader";

export default function LandingPage() {
  return (
    <>
      <title>Warmline · AI sales and support assistant for small businesses</title>
      <meta
        name="description"
        content="Warmline answers customer questions from your FAQ, captures leads and books appointments, always confirming with the customer before it saves anything."
      />
      <PublicHeader />
      <main>
        <Hero />
        <HowItWorks />
        <Features />
        <Safety />
        <CallToAction />
      </main>
      <Footer />
    </>
  );
}
