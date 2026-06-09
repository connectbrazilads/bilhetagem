"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { BarChart3, Gauge, LogOut, Printer, Settings, Users, WalletCards } from "lucide-react";

import { Button } from "@/components/ui";
import { cn } from "@/lib/utils";

const navItems = [
  { href: "/dashboard", label: "Dashboard", icon: Gauge },
  { href: "/users", label: "Usuarios", icon: Users },
  { href: "/printers", label: "Impressoras", icon: Printer },
  { href: "/quotas", label: "Cotas", icon: WalletCards },
  { href: "/reports", label: "Relatorios", icon: BarChart3 },
  { href: "/settings", label: "Configuracoes", icon: Settings }
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const activeItem = navItems.find((item) => item.href === pathname);

  function logout() {
    localStorage.removeItem("token");
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
          {navItems.map((item) => {
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
          <Button variant="outline" onClick={logout} title="Sair">
            <LogOut className="h-4 w-4" />
            Sair
          </Button>
        </header>
        <div className="mx-auto max-w-7xl p-4 md:p-6 lg:p-8">{children}</div>
      </main>
    </div>
  );
}
