// The owner's menu in the top-right corner: who is logged in, and "Log out".
import { ChevronDown, LogOut } from "lucide-react";
import { useAuth } from "@/auth/AuthContext";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { initialsOf } from "@/utils/initials";

export function UserMenu() {
  const { account, logout } = useAuth();

  return (
    <DropdownMenu>
      <DropdownMenuTrigger className="flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-accent">
        <span
          className="grid size-8 place-items-center rounded-full bg-primary-soft text-xs font-semibold text-primary-hover"
          aria-hidden="true"
        >
          {initialsOf(account.business_name)}
        </span>
        <span className="hidden max-w-40 truncate font-medium sm:inline">
          {account.business_name}
        </span>
        <ChevronDown className="size-4 text-muted-foreground" aria-hidden="true" />
        <span className="sr-only">Account menu</span>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuLabel>
          <span className="block font-medium">{account.business_name}</span>
          <span className="block truncate text-xs text-muted-foreground">{account.email}</span>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={() => logout()}>
          <LogOut aria-hidden="true" />
          Log out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
