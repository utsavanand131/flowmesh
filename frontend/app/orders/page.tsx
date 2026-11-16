"use client";

import { useState } from "react";
import AppSidebar from "@/components/AppSidebar";

export default function OrdersPage() {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  return (
    <main className="min-h-screen bg-background text-foreground">
      <div className="flex min-h-screen">
        {/* Desktop Sidebar */}
        <aside className="hidden w-60 shrink-0 border-r border-border bg-surface lg:flex lg:flex-col">
          <AppSidebar activeItem="Orders" />
        </aside>

        {/* Mobile Navigation */}
        {mobileMenuOpen && (
          <div className="fixed inset-0 z-50 lg:hidden">
            <button
              aria-label="Close navigation menu"
              className="absolute inset-0 bg-black/60"
              onClick={() => setMobileMenuOpen(false)}
            />

            <aside className="relative flex h-full w-[85%] max-w-72 flex-col border-r border-border bg-surface">
              <button
                onClick={() => setMobileMenuOpen(false)}
                aria-label="Close menu"
                className="absolute right-4 top-5 z-10 flex h-8 w-8 items-center justify-center rounded-md border border-border text-muted-foreground hover:bg-surface-hover"
              >
                ×
              </button>

              <AppSidebar
                activeItem="Orders"
                onNavigate={() => setMobileMenuOpen(false)}
              />
            </aside>
          </div>
        )}

        {/* Main Content */}
        <section className="min-w-0 flex-1">
          {/* Header */}
          <header className="sticky top-0 z-20 flex items-center gap-3 border-b border-border bg-background/95 px-4 py-4 backdrop-blur sm:px-6 lg:px-8">
            <button
              onClick={() => setMobileMenuOpen(true)}
              aria-label="Open navigation menu"
              className="flex h-9 w-9 items-center justify-center rounded-md border border-border text-lg text-muted-foreground hover:bg-surface-hover lg:hidden"
            >
              ☰
            </button>

            <div>
              <p className="text-xs text-muted">Operations</p>
              <h1 className="mt-0.5 text-lg font-semibold tracking-tight sm:text-xl">
                Orders
              </h1>
            </div>
          </header>

          {/* Orders Content */}
          <div className="mx-auto max-w-[1600px] space-y-8 px-4 py-6 sm:px-6 sm:py-8 lg:px-8">
            <section className="border-b border-border pb-7">
              <p className="text-sm font-medium text-accent">
                FlowMesh / Operations
              </p>

              <h2 className="mt-2 text-2xl font-semibold tracking-tight sm:text-3xl">
                Order Management
              </h2>

              <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">
                Track orders, monitor processing status, and follow delivery
                progress across the order pipeline.
              </p>
            </section>

            <section className="rounded-lg border border-border bg-surface p-6">
              <h3 className="text-sm font-semibold">Orders workspace</h3>
              <p className="mt-2 text-sm text-muted-foreground">
                Your order management interface will appear here.
              </p>
            </section>
          </div>
        </section>
      </div>
    </main>
  );
}
