"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@/contexts/AuthContext";

interface NavigationItem {
  label: string;
  icon: string;
  href: string;
}

interface NavigationGroup {
  heading: string;
  items: NavigationItem[];
}

interface AppSidebarProps {
  activeItem: string;
  onNavigate?: () => void;
}

const customerNavigation: NavigationGroup[] = [
  {
    heading: "Operations",
    items: [
      { label: "Dashboard", icon: "▦", href: "/" },
      { label: "My Orders", icon: "□", href: "/orders" },
      { label: "Deliveries", icon: "↗", href: "#" },
    ],
  },
];

const adminNavigation: NavigationGroup[] = [
  {
    heading: "Operations",
    items: [
      { label: "Dashboard", icon: "▦", href: "/" },
      { label: "All Orders", icon: "□", href: "/orders" },
      { label: "Deliveries", icon: "↗", href: "#" },
    ],
  },
  {
    heading: "System",
    items: [
      { label: "Services", icon: "◈", href: "/services" },
      { label: "Event Stream", icon: "≋", href: "#" },
    ],
  },
];

export default function AppSidebar({
  activeItem,
  onNavigate,
}: AppSidebarProps) {
  const { user, logout } = useAuth();
  const router = useRouter();

  const [loggingOut, setLoggingOut] = useState(false);
  const [logoutError, setLogoutError] = useState("");
  const [avatarFailed, setAvatarFailed] = useState(false);

  const isAdmin = user?.role === "ADMIN";

  const navigation = isAdmin ? adminNavigation : customerNavigation;

  const displayName = user?.name?.trim() || "FlowMesh User";
  const avatarUrl = user?.avatar_url;

  const initials = displayName
    .split(/\s+/)
    .map((part) => part[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();

  useEffect(() => {
    setAvatarFailed(false);
  }, [avatarUrl]);

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

      {/* Role-Based Navigation */}
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

      {/* User Profile */}
      <div className="border-t border-border px-4 py-4">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center overflow-hidden rounded-full border border-accent/25 bg-accent/10 text-sm font-semibold text-accent">
            {avatarUrl && !avatarFailed ? (
              <img
                src={avatarUrl}
                alt={`${displayName}'s profile`}
                referrerPolicy="no-referrer"
                onError={() => setAvatarFailed(true)}
                className="h-full w-full object-cover"
              />
            ) : (
              initials || "U"
            )}
          </div>

          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium text-foreground">
              {displayName}
            </p>

            <p className="truncate text-xs text-muted">
              {user?.email ?? "No email available"}
            </p>
          </div>
        </div>

        <div className="mt-3">
          <span className="inline-flex rounded-md border border-accent/20 bg-accent/10 px-2 py-1 text-[10px] font-semibold tracking-wide text-accent">
            {user?.role ?? "USER"}
          </span>
        </div>
      </div>

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
