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

  function logout() {
    localStorage.removeItem("token");
    router.push("/");
  }

  return (
    <div className="min-h-screen">
      <aside className="fixed left-0 top-0 hidden h-screen w-64 border-r bg-white md:block">
        <div className="flex h-14 items-center border-b px-4 font-semibold">PrintBilling</div>
        <nav className="space-y-1 p-3">
          {navItems.map((item) => {
            const Icon = item.icon;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "flex h-9 items-center gap-3 rounded-md px-3 text-sm text-muted-foreground hover:bg-muted hover:text-foreground",
                  pathname === item.href && "bg-muted text-foreground"
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
        <header className="sticky top-0 z-10 flex h-14 items-center justify-between border-b bg-white px-4">
          <div className="text-sm font-medium">Bilhetagem de Impressao</div>
          <Button variant="ghost" onClick={logout} title="Sair">
            <LogOut className="h-4 w-4" />
            Sair
          </Button>
        </header>
        <div className="mx-auto max-w-7xl p-4 md:p-6">{children}</div>
      </main>
    </div>
  );
}
