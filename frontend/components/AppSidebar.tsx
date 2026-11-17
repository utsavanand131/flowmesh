"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@/contexts/AuthContext";

const navigation = [
  {
    heading: "Operations",
    items: [
      { label: "Dashboard", icon: "▦", href: "/" },
      { label: "Orders", icon: "□", href: "/orders" },
      { label: "Deliveries", icon: "↗", href: "#" },
    ],
  },
  {
    heading: "System",
    items: [
      { label: "Services", icon: "◈", href: "#" },
      { label: "Event Stream", icon: "≋", href: "#" },
    ],
  },
];

interface AppSidebarProps {
  activeItem: string;
  onNavigate?: () => void;
}

export default function AppSidebar({
  activeItem,
  onNavigate,
}: AppSidebarProps) {
  const { logout } = useAuth();
  const router = useRouter();

  const [loggingOut, setLoggingOut] = useState(false);
  const [logoutError, setLogoutError] = useState("");

  async function handleLogout() {
    setLoggingOut(true);
    setLogoutError("");

    try {
      await logout();
      onNavigate?.();
      router.replace("/login");
      router.refresh();
    } catch {
      setLogoutError("Unable to log out. Please try again.");
      setLoggingOut(false);
    }
  }

  return (
    <>
      {/* Brand */}
      <div className="border-b border-border px-5 py-6">
        <Link href="/" className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-accent/10 text-xl font-semibold text-accent">
            F
          </div>

          <div>
            <div className="text-lg font-semibold tracking-tight text-foreground">
              FlowMesh
            </div>
            <div className="mt-0.5 text-xs text-muted">
              Distributed Order System
            </div>
          </div>
        </Link>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-3 py-6">
        {navigation.map((group) => (
          <div key={group.heading} className="mb-8">
            <div className="mb-3 px-3 text-xs font-medium text-muted">
              {group.heading}
            </div>

            <div className="space-y-1">
              {group.items.map((item) => {
                const active = item.label === activeItem;

                return (
                  <Link
                    key={item.label}
                    href={item.href}
                    onClick={onNavigate}
                    className={`flex w-full items-center gap-3 rounded-md px-3 py-2.5 text-left text-sm transition ${
                      active
                        ? "bg-accent/10 font-medium text-accent"
                        : "text-muted-foreground hover:bg-surface-hover hover:text-foreground"
                    }`}
                  >
                    <span className="w-5 text-center text-base">
                      {item.icon}
                    </span>
                    {item.label}
                  </Link>
                );
              })}
            </div>
          </div>
        ))}
      </nav>

      {/* Logout */}
      <div className="border-t border-border px-3 py-4">
        <button
          type="button"
          onClick={handleLogout}
          disabled={loggingOut}
          className="flex w-full items-center gap-3 rounded-md px-3 py-2.5 text-sm text-muted-foreground transition hover:bg-danger/10 hover:text-danger disabled:cursor-not-allowed disabled:opacity-60"
        >
          <span className="w-5 text-center text-base">↪</span>
          {loggingOut ? "Signing out..." : "Logout"}
        </button>

        {logoutError && (
          <p className="mt-2 px-3 text-xs text-danger">{logoutError}</p>
        )}
      </div>

      {/* System Status */}
      <div className="border-t border-border px-5 py-5">
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <span className="h-2 w-2 rounded-full bg-success" />
          System status
          <span className="ml-auto text-success">Online</span>
        </div>

        <div className="mt-2 text-xs text-muted">FlowMesh v1.0.0</div>
      </div>
    </>
  );
}
