"use client";

import { useEffect, useMemo, useState } from "react";
import { Gauge, WalletCards } from "lucide-react";

import { ProtectedPage } from "@/components/protected-page";
import { Surface } from "@/components/ui";
import { apiFetch } from "@/lib/api";

type QuotaRow = {
  id: number;
  username: string;
  year: number;
  month: number;
  monthly_limit: number;
  used_pages: number;
  remaining_pages: number;
};

export default function QuotasPage() {
  const [quotas, setQuotas] = useState<QuotaRow[]>([]);

  useEffect(() => {
    const token = localStorage.getItem("token");
    if (token) apiFetch<QuotaRow[]>("/quotas", token).then(setQuotas).catch(() => setQuotas([]));
  }, []);

  const totals = useMemo(() => {
    return quotas.reduce(
      (acc, quota) => {
        acc.limit += quota.monthly_limit;
        acc.used += quota.used_pages;
        acc.remaining += quota.remaining_pages;
        return acc;
      },
      { limit: 0, used: 0, remaining: 0 }
    );
  }, [quotas]);

  return (
    <ProtectedPage>
      <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Cotas</h1>
          <p className="mt-1 text-sm text-muted-foreground">Acompanhe consumo, limite e saldo de paginas por usuario.</p>
        </div>
      </div>

      <div className="mb-4 grid gap-4 md:grid-cols-3">
        <Summary label="Limite total" value={totals.limit} icon={WalletCards} />
        <Summary label="Paginas usadas" value={totals.used} icon={Gauge} />
        <Summary label="Saldo restante" value={totals.remaining} icon={WalletCards} />
      </div>

      <Surface className="overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-muted/80 text-left text-xs uppercase tracking-wide text-muted-foreground">
            <tr>
              <th className="p-4">Usuario</th>
              <th className="p-4">Periodo</th>
              <th className="p-4">Uso</th>
              <th className="p-4 text-right">Limite</th>
              <th className="p-4 text-right">Saldo</th>
            </tr>
          </thead>
          <tbody>
            {quotas.map((quota) => {
              const percent = quota.monthly_limit > 0 ? Math.min((quota.used_pages / quota.monthly_limit) * 100, 100) : 0;
              return (
                <tr key={quota.id} className="border-t bg-white transition-colors hover:bg-muted/30">
                  <td className="p-4 font-semibold">{quota.username}</td>
                  <td className="p-4 text-muted-foreground">
                    {String(quota.month).padStart(2, "0")}/{quota.year}
                  </td>
                  <td className="p-4">
                    <div className="flex items-center gap-3">
                      <div className="h-2 w-full max-w-[260px] overflow-hidden rounded-full bg-muted">
                        <div className="h-full rounded-full bg-primary" style={{ width: `${percent}%` }} />
                      </div>
                      <span className="w-14 text-xs font-semibold text-muted-foreground">{percent.toFixed(0)}%</span>
                    </div>
                  </td>
                  <td className="p-4 text-right font-medium">{quota.monthly_limit.toLocaleString("pt-BR")}</td>
                  <td className="p-4 text-right font-semibold">{quota.remaining_pages.toLocaleString("pt-BR")}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </Surface>
    </ProtectedPage>
  );
}

function Summary({ label, value, icon: Icon }: { label: string; value: number; icon: typeof Gauge }) {
  return (
    <Surface className="p-5">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-muted-foreground">{label}</span>
        <div className="flex h-9 w-9 items-center justify-center rounded-md bg-primary/10 text-primary">
          <Icon className="h-4 w-4" />
        </div>
      </div>
      <div className="mt-3 text-3xl font-semibold">{value.toLocaleString("pt-BR")}</div>
    </Surface>
  );
}
