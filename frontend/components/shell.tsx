"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  Activity,
  BarChart3,
  Building2,
  ChevronRight,
  ClipboardCheck,
  Download,
  Gauge,
  History,
  LogOut,
  Menu,
  MonitorCog,
  Printer,
  Settings,
  ShieldCheck,
  Users,
  WalletCards,
  X
} from "lucide-react";

import { Button } from "@/components/ui";
import { apiFetch, clearAuthStorage, getCurrentRole } from "@/lib/api";
import { cn } from "@/lib/utils";

const navItems = [
  { href: "/dashboard", label: "Dashboard", description: "Resumo operacional", icon: Gauge, roles: ["admin", "manager"], group: "Operacao" },
  { href: "/deployment", label: "Implantacao", description: "Checklist de piloto", icon: ClipboardCheck, roles: ["admin", "manager"], group: "Operacao" },
  { href: "/agents", label: "Agents", description: "PCs e captura", icon: MonitorCog, roles: ["admin", "manager"], group: "Operacao" },
  { href: "/printers", label: "Impressoras", description: "Parque e SNMP", icon: Printer, roles: ["admin", "manager"], group: "Operacao" },
  { href: "/users", label: "Usuarios", description: "Pessoas e perfis", icon: Users, roles: ["admin", "manager"], group: "Cadastros" },
  { href: "/organizations", label: "Empresas", description: "Clientes SaaS", icon: Building2, roles: ["admin"], group: "Cadastros" },
  { href: "/policies", label: "Politicas", description: "Regras de impressao", icon: ShieldCheck, roles: ["admin", "manager"], group: "Governanca" },
  { href: "/quotas", label: "Cotas", description: "Limites e consumo", icon: WalletCards, roles: ["admin", "manager"], group: "Governanca" },
  { href: "/reports", label: "Relatorios", description: "Fechamento e custos", icon: BarChart3, roles: ["admin", "manager"], group: "Governanca" },
  { href: "/audit", label: "Auditoria", description: "Rastreabilidade", icon: History, roles: ["admin", "manager"], group: "Governanca" },
  { href: "/downloads", label: "Downloads", description: "Agent e instaladores", icon: Download, roles: ["admin", "manager"], group: "Plataforma" },
  { href: "/settings", label: "Configuracoes", description: "Modulos e integracoes", icon: Settings, roles: ["admin"], group: "Plataforma" }
];

const navGroups = ["Operacao", "Cadastros", "Governanca", "Plataforma"];

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
  const [mobileOpen, setMobileOpen] = useState(false);
  const visibleNavItems = navItems.filter((item) => !role || item.roles.includes(role));
  const visibleNavGroups = navGroups
    .map((group) => ({ group, items: visibleNavItems.filter((item) => item.group === group) }))
    .filter((section) => section.items.length > 0);

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

  useEffect(() => {
    setMobileOpen(false);
  }, [pathname]);

  function logout() {
    clearAuthStorage();
    router.push("/");
  }

  return (
    <div className="min-h-screen bg-background">
      <aside className="fixed left-0 top-0 hidden h-screen w-72 border-r border-slate-200/80 bg-white/95 text-slate-950 shadow-sm backdrop-blur md:flex md:flex-col">
        <div className="flex h-16 items-center gap-3 border-b border-slate-200/80 px-5">
          <div className="flex h-10 w-10 items-center justify-center rounded-md bg-slate-950 text-sm font-bold text-white shadow-sm">PB</div>
          <div className="min-w-0">
            <div className="truncate text-sm font-bold">PrintBilling</div>
            <div className="truncate text-xs text-muted-foreground">SaaS de bilhetagem</div>
          </div>
        </div>
        {organizationSlug ? (
          <div className="mx-3 mt-3 rounded-lg border bg-slate-50/90 p-3 text-xs shadow-sm">
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <div className="truncate font-bold">{organizationName || organizationSlug}</div>
                {organizationName ? <div className="mt-0.5 truncate text-muted-foreground">{organizationSlug}</div> : null}
              </div>
              {billingStatusLabel(organizationBillingStatus) ? (
                <span className={cn("shrink-0 rounded-full border px-1.5 py-0.5 text-[10px] font-bold", billingStatusClass(organizationBillingStatus))}>
                  {billingStatusLabel(organizationBillingStatus)}
                </span>
              ) : null}
            </div>
            <div className="mt-3 flex items-center gap-2 rounded-md border bg-white px-2 py-1.5 text-[11px] font-semibold text-muted-foreground">
              <Activity className="h-3.5 w-3.5 text-emerald-600" />
              Ambiente conectado
            </div>
          </div>
        ) : null}
        <nav className="flex-1 space-y-5 overflow-y-auto px-3 py-4">
          {visibleNavGroups.map((section) => (
            <div key={section.group}>
              <div className="px-3 pb-2 text-[11px] font-bold uppercase text-slate-400">{section.group}</div>
              <div className="space-y-1">
                {section.items.map((item) => (
                  <NavLink key={item.href} item={item} active={pathname === item.href} />
                ))}
              </div>
            </div>
          ))}
        </nav>
        <div className="border-t border-slate-200/80 p-3">
          <div className="flex items-center gap-3 rounded-lg bg-slate-50 px-3 py-2 text-xs">
            <div className="flex h-8 w-8 items-center justify-center rounded-md bg-white font-bold text-primary shadow-sm">{roleInitial(role)}</div>
            <div className="min-w-0">
              <div className="truncate font-bold">{roleLabel(role)}</div>
              <div className="truncate text-muted-foreground">Sessao protegida</div>
            </div>
          </div>
        </div>
      </aside>
      {mobileOpen ? (
        <div className="fixed inset-0 z-40 md:hidden">
          <button
            type="button"
            aria-label="Fechar menu"
            className="absolute inset-0 bg-slate-950/50"
            onClick={() => setMobileOpen(false)}
          />
          <aside className="relative flex h-full w-80 max-w-[88vw] flex-col border-r border-slate-200 bg-white text-slate-950 shadow-xl">
            <div className="flex h-16 items-center justify-between gap-3 border-b border-slate-200 px-5">
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-md bg-slate-950 text-sm font-bold text-white">PB</div>
                <div>
                  <div className="text-sm font-semibold">PrintBilling</div>
                  <div className="text-xs text-muted-foreground">SaaS de bilhetagem</div>
                </div>
              </div>
              <button
                type="button"
                aria-label="Fechar menu"
                className="flex h-9 w-9 items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground"
                onClick={() => setMobileOpen(false)}
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            {organizationSlug ? (
              <div className="border-b border-slate-200 px-5 py-3 text-xs text-muted-foreground">
                <div className="font-semibold text-foreground">{organizationName || organizationSlug}</div>
                {organizationName ? <div className="mt-0.5 text-muted-foreground">{organizationSlug}</div> : null}
                {billingStatusLabel(organizationBillingStatus) ? (
                  <span className={cn("mt-2 inline-flex rounded-full border px-1.5 py-0.5 text-[10px] font-bold", billingStatusClass(organizationBillingStatus))}>
                    {billingStatusLabel(organizationBillingStatus)}
                  </span>
                ) : null}
              </div>
            ) : null}
            <nav className="flex-1 space-y-5 overflow-y-auto px-3 py-4">
              {visibleNavGroups.map((section) => (
                <div key={section.group}>
                  <div className="px-3 pb-2 text-[11px] font-bold uppercase text-slate-400">{section.group}</div>
                  <div className="space-y-1">
                    {section.items.map((item) => (
                      <NavLink key={item.href} item={item} active={pathname === item.href} />
                    ))}
                  </div>
                </div>
              ))}
            </nav>
          </aside>
        </div>
      ) : null}
      <main className="md:pl-72">
        <header className="sticky top-0 z-10 flex h-16 items-center justify-between border-b border-slate-200/80 bg-white/88 px-4 shadow-sm shadow-slate-200/40 backdrop-blur md:px-6">
          <div className="flex min-w-0 items-center gap-3">
            <button
              type="button"
              aria-label="Abrir menu"
              className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md border bg-card text-muted-foreground md:hidden"
              onClick={() => setMobileOpen(true)}
            >
              <Menu className="h-4 w-4" />
            </button>
            <div className="min-w-0">
              <div className="truncate text-sm font-bold">{activeItem?.label ?? "Painel"}</div>
              <div className="truncate text-xs text-muted-foreground">{activeItem?.description ?? "Operacao em tempo real"}</div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {organizationSlug ? (
              <div className="hidden max-w-[360px] items-center gap-2 rounded-md border bg-white/90 px-3 py-2 text-xs font-semibold text-muted-foreground shadow-sm sm:flex">
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
        <div className="mx-auto max-w-[1440px] p-4 md:p-6 lg:p-8">{children}</div>
      </main>
    </div>
  );
}

type NavItem = (typeof navItems)[number];

function NavLink({ item, active }: { item: NavItem; active: boolean }) {
  const Icon = item.icon;
  return (
    <Link
      href={item.href}
      className={cn(
        "group flex min-h-11 items-center gap-3 rounded-md px-3 py-2 text-sm font-semibold text-muted-foreground transition-all hover:bg-primary/10 hover:text-primary",
        active && "bg-primary text-white shadow-sm shadow-primary/20 hover:bg-primary hover:text-white"
      )}
    >
      <span className={cn("flex h-8 w-8 shrink-0 items-center justify-center rounded-md border bg-white text-slate-500 transition-all group-hover:border-primary/20 group-hover:text-primary", active && "border-white/15 bg-white/15 text-white")}>
        <Icon className="h-4 w-4" />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate">{item.label}</span>
        <span className={cn("block truncate text-[11px] font-medium text-muted-foreground/80", active && "text-white/75")}>{item.description}</span>
      </span>
      {active ? <ChevronRight className="h-4 w-4 shrink-0 text-white/80" /> : null}
    </Link>
  );
}

function billingStatusLabel(status: string) {
  if (status === "trial") return "Teste";
  if (status === "active") return "Em dia";
  if (status === "past_due") return "Em atraso";
  if (status === "suspended") return "Suspenso";
  return "";
}

function billingStatusClass(status: string) {
  if (status === "active") return "border-emerald-200 bg-emerald-50 text-emerald-700";
  if (status === "past_due") return "border-amber-200 bg-amber-50 text-amber-700";
  if (status === "suspended") return "border-red-200 bg-red-50 text-red-700";
  return "border-blue-200 bg-blue-50 text-blue-700";
}

function roleLabel(role: string) {
  if (role === "admin") return "Administrador";
  if (role === "manager") return "Gestor";
  if (role === "user") return "Usuario";
  return "Operador";
}

function roleInitial(role: string) {
  if (role === "admin") return "A";
  if (role === "manager") return "G";
  if (role === "user") return "U";
  return "P";
}
