// The frame around every owner page: a sidebar on wide screens, a tab row under the top bar
// on phones, and the page itself in <main>. The "Skip to content" link lets keyboard users
// jump past the navigation.
import { HelpCircle, Link2 } from "lucide-react";
import { NavLink, Outlet } from "react-router";
import { cn } from "@/utils/cn";
import { Logo } from "./Logo";
import { UserMenu } from "./UserMenu";

const NAV = [
  { to: "/app/integrations", label: "Chat links", icon: Link2 },
  { to: "/app/faq", label: "FAQ", icon: HelpCircle },
];

function navClasses({ isActive }) {
  return cn(
    "flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-colors",
    isActive
      ? "bg-primary-soft text-primary-hover"
      : "text-muted-foreground hover:bg-accent hover:text-foreground",
  );
}

function NavLinks({ className }) {
  return (
    <ul className={className}>
      {NAV.map(({ to, label, icon: Icon }) => (
        <li key={to}>
          <NavLink to={to} className={navClasses}>
            <Icon className="size-4" aria-hidden="true" />
            {label}
          </NavLink>
        </li>
      ))}
    </ul>
  );
}

export function AppShell() {
  return (
    <div className="min-h-dvh md:grid md:grid-cols-[14rem_1fr]">
      <a
        href="#main"
        className="sr-only z-50 rounded-md bg-card px-3 py-2 focus:not-sr-only focus:fixed focus:top-2 focus:left-2"
      >
        Skip to content
      </a>
      <aside className="hidden border-r bg-card px-3 py-5 md:block">
        <Logo to="/app/integrations" className="px-3" />
        <nav aria-label="Main" className="mt-8">
          <NavLinks className="grid gap-1" />
        </nav>
      </aside>

      <div className="flex min-w-0 flex-col">
        <header className="flex h-14 items-center justify-between border-b bg-card px-4 md:justify-end md:px-8">
          <Logo to="/app/integrations" className="md:hidden" />
          <UserMenu />
        </header>
        <nav aria-label="Main" className="border-b bg-card px-2 py-1.5 md:hidden">
          <NavLinks className="flex gap-1" />
        </nav>
        <main
          id="main"
          tabIndex={-1}
          className="mx-auto w-full max-w-5xl flex-1 px-4 py-8 outline-none md:px-8"
        >
          <Outlet />
        </main>
      </div>
    </div>
  );
}
