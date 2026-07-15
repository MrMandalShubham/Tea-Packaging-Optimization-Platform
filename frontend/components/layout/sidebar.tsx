"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { cn } from "@/lib/utils";
import {
  LayoutDashboard,
  FlaskConical,
  GitCompare,
  History,
  Package,
  Menu,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";

const navItems = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/simulation", label: "New Simulation", icon: FlaskConical },
  { href: "/compare", label: "Compare", icon: GitCompare },
  { href: "/history", label: "History", icon: History },
];

export function AppSidebar() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);

  const links = navItems.map(({ href, label, icon: Icon }) => {
    const active = pathname === href || (href !== "/" && pathname.startsWith(href));
    return (
      <Link
        key={href}
        href={href}
        onClick={() => setOpen(false)}
        className={cn(
          "flex items-center gap-3 px-3 py-2.5 rounded-md text-sm font-medium transition-colors",
          active
            ? "bg-primary/10 text-primary"
            : "text-muted-foreground hover:bg-accent hover:text-accent-foreground"
        )}
      >
        <Icon className="h-4 w-4" />
        {label}
      </Link>
    );
  });

  return (
    <>
      {/* Mobile hamburger */}
      <div className="lg:hidden fixed top-0 left-0 z-50 p-3">
        <Button variant="ghost" size="icon" onClick={() => setOpen(true)}>
          <Menu className="h-5 w-5" />
        </Button>
      </div>

      {/* Mobile overlay */}
      {open && (
        <div
          className="lg:hidden fixed inset-0 z-40 bg-black/50"
          onClick={() => setOpen(false)}
        />
      )}

      {/* Sidebar — hidden on mobile unless open */}
      <aside
        className={cn(
          "fixed lg:static inset-y-0 left-0 z-50 w-60 border-r bg-card flex flex-col transition-transform",
          "lg:translate-x-0",
          open ? "translate-x-0" : "-translate-x-full"
        )}
      >
        <div className="h-16 flex items-center gap-3 px-6 border-b">
          <Button variant="ghost" size="icon" className="lg:hidden -ml-2" onClick={() => setOpen(false)}>
            <X className="h-4 w-4" />
          </Button>
          <Package className="h-6 w-6 text-primary" />
          <span className="font-bold text-lg">TeaPackOpt</span>
        </div>

        <nav className="flex-1 p-3 space-y-1">{links}</nav>

        <div className="p-4 border-t">
          <p className="text-xs text-muted-foreground text-center">
            AI-Powered Packaging Optimization
          </p>
        </div>
      </aside>
    </>
  );
}
