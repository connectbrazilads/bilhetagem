"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { BarChart3, Building2, Download, Gauge, History, LogOut, MonitorCog, Printer, Settings, ShieldCheck, Users, WalletCards } from "lucide-react";

import { Button } from "@/components/ui";
import { apiFetch, getCurrentRole } from "@/lib/api";
import { cn } from "@/lib/utils";

const navItems = [
  { href: "/dashboard", label: "Dashboard", icon: Gauge, roles: ["admin", "manager"] },
  { href: "/organizations", label: "Empresas", icon: Building2, roles: ["admin"] },
  { href: "/users", label: "Usuarios", icon: Users, roles: ["admin", "manager"] },
  { href: "/agents", label: "Agents", icon: MonitorCog, roles: ["admin", "manager"] },
  { href: "/printers", label: "Impressoras", icon: Printer, roles: ["admin", "manager"] },
  { href: "/policies", label: "Politicas", icon: ShieldCheck, roles: ["admin", "manager"] },
  { href: "/quotas", label: "Cotas", icon: WalletCards, roles: ["admin", "manager"] },
  { href: "/reports", label: "Relatorios", icon: BarChart3, roles: ["admin", "manager"] },
  { href: "/audit", label: "Auditoria", icon: History, roles: ["admin", "manager"] },
  { href: "/downloads", label: "Downloads", icon: Download, roles: ["admin", "manager"] },
  { href: "/settings", label: "Configuracoes", icon: Settings, roles: ["admin"] }
];

type AuthContext = {
  username: string;
  full_name: string;
  role: string;
  organization_id: number;
  organization_slug: string;
  organization_name: string;
  organization_billing_status: "trial" | "active" | "past_due" | "suspended";
};

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const activeItem = navItems.find((item) => item.href === pathname);
  const [organizationSlug, setOrganizationSlug] = useState("");
  const [organizationName, setOrganizationName] = useState("");
  const [organizationBillingStatus, setOrganizationBillingStatus] = useState("");
  const [role, setRole] = useState("");
  const visibleNavItems = navItems.filter((item) => !role || item.roles.includes(role));

  useEffect(() => {
    setOrganizationSlug(localStorage.getItem("organization_slug") || "");
    setOrganizationName(localStorage.getItem("organization_name") || "");
    setOrganizationBillingStatus(localStorage.getItem("organization_billing_status") || "");
    const token = localStorage.getItem("token");
    if (!token) return;
    setRole(getCurrentRole(token) || "");
    let active = true;
    apiFetch<AuthContext>("/auth/me", token)
      .then((context) => {
        if (!active) return;
        setOrganizationSlug(context.organization_slug);
        setOrganizationName(context.organization_name);
        setOrganizationBillingStatus(context.organization_billing_status);
        setRole(context.role);
        localStorage.setItem("organization_slug", context.organization_slug);
        localStorage.setItem("organization_name", context.organization_name);
        localStorage.setItem("organization_billing_status", context.organization_billing_status);
      })
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, []);

  function logout() {
    localStorage.removeItem("token");
    localStorage.removeItem("organization_billing_status");
    router.push("/");
  }

  return (
    <div className="min-h-screen bg-background">
      <aside className="fixed left-0 top-0 hidden h-screen w-64 border-r border-slate-900/10 bg-slate-950 text-white md:block">
        <div className="flex h-16 items-center gap-3 border-b border-white/10 px-5">
          <div className="flex h-9 w-9 items-center justify-center rounded-md bg-primary text-sm font-bold text-white">PB</div>
          <div>
            <div className="text-sm font-semibold">PrintBilling</div>
            <div className="text-xs text-slate-400">Controle de impressao</div>
          </div>
        </div>
        <nav className="space-y-1 p-3">
          {visibleNavItems.map((item) => {
            const Icon = item.icon;
            const active = pathname === item.href;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "flex h-10 items-center gap-3 rounded-md px-3 text-sm text-slate-300 transition-colors hover:bg-white/10 hover:text-white",
                  active && "bg-white text-slate-950 shadow-sm hover:bg-white hover:text-slate-950"
                )}
              >
                <Icon className="h-4 w-4" />
                {item.label}
              </Link>
            );
          })}
        </nav>
      </aside>
      <main className="md:pl-64">
        <header className="sticky top-0 z-10 flex h-16 items-center justify-between border-b bg-white/90 px-4 backdrop-blur md:px-6">
          <div>
            <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Bilhetagem de Impressao</div>
            <div className="text-sm font-semibold">{activeItem?.label ?? "Painel"}</div>
          </div>
          <div className="flex items-center gap-2">
            {organizationSlug ? (
              <div className="hidden max-w-[260px] items-center gap-2 rounded-md border bg-muted/40 px-3 py-2 text-xs font-semibold text-muted-foreground sm:flex">
                <Building2 className="h-3.5 w-3.5" />
                <span className="truncate">{organizationName || organizationSlug}</span>
                {organizationName ? <span className="text-[10px] font-medium text-muted-foreground/80">/{organizationSlug}</span> : null}
                {billingStatusLabel(organizationBillingStatus) ? (
                  <span className={cn("rounded-full border px-1.5 py-0.5 text-[10px] font-bold", billingStatusClass(organizationBillingStatus))}>
                    {billingStatusLabel(organizationBillingStatus)}
                  </span>
                ) : null}
              </div>
            ) : null}
            <Button variant="outline" onClick={logout} title="Sair">
              <LogOut className="h-4 w-4" />
              Sair
            </Button>
          </div>
        </header>
        <div className="mx-auto max-w-7xl p-4 md:p-6 lg:p-8">{children}</div>
      </main>
    </div>
  );
}

function billingStatusLabel(status: string) {
  if (status === "trial") return "Teste";
  if (status === "past_due") return "Em atraso";
  return "";
}

function billingStatusClass(status: string) {
  if (status === "past_due") return "border-amber-200 bg-amber-50 text-amber-700";
  return "border-blue-200 bg-blue-50 text-blue-700";
}
