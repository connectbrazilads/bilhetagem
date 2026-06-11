"use client";

import { useEffect, useMemo, useState, type ComponentType } from "react";
import { AlertTriangle, Check, Edit, Gauge, TrendingUp, Users, WalletCards, X } from "lucide-react";

import { ProtectedPage } from "@/components/protected-page";
import { Button, Input, Surface } from "@/components/ui";
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
  const [editingId, setEditingId] = useState<number | null>(null);
  const [draftLimit, setDraftLimit] = useState("");
  const [savingId, setSavingId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    const token = localStorage.getItem("token");
    if (!token) return;
    await apiFetch<QuotaRow[]>("/quotas", token).then(setQuotas).catch(() => setQuotas([]));
  }

  useEffect(() => {
    load();
  }, []);

  function startEdit(quota: QuotaRow) {
    setEditingId(quota.id);
    setDraftLimit(String(quota.monthly_limit));
    setError(null);
  }

  function cancelEdit() {
    setEditingId(null);
    setDraftLimit("");
    setError(null);
  }

  async function saveQuota(quota: QuotaRow) {
    const token = localStorage.getItem("token");
    if (!token) return;
    const monthlyLimit = Number(draftLimit);
    if (!Number.isFinite(monthlyLimit) || monthlyLimit < 0) {
      setError("Informe um limite mensal valido.");
      return;
    }
    setSavingId(quota.id);
    setError(null);
    try {
      const updated = await apiFetch<QuotaRow>(`/quotas/${quota.id}`, token, {
        method: "PUT",
        body: JSON.stringify({ monthly_limit: Math.trunc(monthlyLimit) }),
      });
      setQuotas((current) => current.map((item) => (item.id === updated.id ? updated : item)));
      setEditingId(null);
      setDraftLimit("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao atualizar cota");
    } finally {
      setSavingId(null);
    }
  }

  const totals = useMemo(() => {
    return quotas.reduce(
      (acc, quota) => {
        acc.limit += quota.monthly_limit;
        acc.used += quota.used_pages;
        acc.remaining += quota.remaining_pages;
        if (quota.remaining_pages <= 0) acc.exhausted += 1;
        if (quota.monthly_limit > 0 && quota.used_pages / quota.monthly_limit >= 0.8) acc.warning += 1;
        return acc;
      },
      { limit: 0, used: 0, remaining: 0, exhausted: 0, warning: 0 }
    );
  }, [quotas]);
  const usedPercent = totals.limit > 0 ? Math.min(Math.round((totals.used / totals.limit) * 100), 100) : 0;
  const avgLimit = quotas.length > 0 ? Math.round(totals.limit / quotas.length) : 0;

  return (
    <ProtectedPage>
      <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Cotas</h1>
          <p className="mt-1 text-sm text-muted-foreground">Acompanhe consumo, limite e saldo de paginas por usuario.</p>
        </div>
      </div>

      <Surface className="mb-6 overflow-hidden">
        <div className="grid gap-0 lg:grid-cols-[1.15fr_0.85fr]">
          <div className="border-b p-5 lg:border-b-0 lg:border-r">
            <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
              <div>
                <div className="text-xs font-bold uppercase text-muted-foreground">Controle mensal</div>
                <div className="mt-1 text-xl font-bold">Consumo de cotas</div>
              </div>
              <span className={`inline-flex rounded-full border px-2.5 py-1 text-xs font-bold ${totals.exhausted || totals.warning ? "border-amber-200 bg-amber-50 text-amber-700" : "border-emerald-200 bg-emerald-50 text-emerald-700"}`}>
                {totals.exhausted || totals.warning ? "Acompanhar usuarios" : "Uso saudavel"}
              </span>
            </div>
            <div className="mb-3 flex flex-wrap items-end gap-3">
              <div className="text-4xl font-bold">{usedPercent}%</div>
              <div className="pb-1 text-sm text-muted-foreground">
                {totals.used.toLocaleString("pt-BR")} de {totals.limit.toLocaleString("pt-BR")} paginas consumidas
              </div>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-slate-100">
              <div
                className={`h-full rounded-full ${usedPercent >= 90 ? "bg-red-500" : usedPercent >= 80 ? "bg-amber-500" : "bg-blue-600"}`}
                style={{ width: `${usedPercent}%` }}
              />
            </div>
            <div className="mt-4 grid gap-2 sm:grid-cols-3">
              <QuotaSignal icon={Users} label="Usuarios" value={quotas.length.toLocaleString("pt-BR")} detail="Com cota no periodo" />
              <QuotaSignal icon={WalletCards} label="Media" value={`${avgLimit.toLocaleString("pt-BR")} pag.`} detail="Limite medio por usuario" />
              <QuotaSignal icon={TrendingUp} label="Saldo" value={`${totals.remaining.toLocaleString("pt-BR")} pag.`} detail="Ainda disponivel" />
            </div>
          </div>
          <div className="grid gap-0 sm:grid-cols-2">
            <QuotaTile icon={AlertTriangle} label="Acima de 80%" value={totals.warning} tone={totals.warning ? "warn" : "ok"} detail="Usuarios proximos do limite" />
            <QuotaTile icon={X} label="Saldo zerado" value={totals.exhausted} tone={totals.exhausted ? "danger" : "ok"} detail="Usuarios sem paginas restantes" />
            <QuotaTile icon={Gauge} label="Usadas" value={totals.used} tone="info" detail="Paginas consumidas no mes" />
            <QuotaTile icon={WalletCards} label="Restantes" value={totals.remaining} tone={totals.remaining ? "ok" : "warn"} detail="Saldo operacional do periodo" />
          </div>
        </div>
      </Surface>

      <div className="mb-4 grid gap-4 md:grid-cols-3">
        <Summary label="Limite total" value={totals.limit} icon={WalletCards} />
        <Summary label="Paginas usadas" value={totals.used} icon={Gauge} />
        <Summary label="Saldo restante" value={totals.remaining} icon={WalletCards} />
      </div>

      {error ? <Surface className="mb-4 border-red-200 bg-red-50 p-3 text-sm text-red-800">{error}</Surface> : null}

      <Surface className="overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-muted/80 text-left text-xs uppercase tracking-wide text-muted-foreground">
            <tr>
              <th className="p-4">Usuario</th>
              <th className="p-4">Periodo</th>
              <th className="p-4">Uso</th>
              <th className="p-4 text-right">Limite</th>
              <th className="p-4 text-right">Saldo</th>
              <th className="p-4 text-right">Acoes</th>
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
                  <td className="p-4 text-right font-medium">
                    {editingId === quota.id ? (
                      <Input
                        className="ml-auto w-28 text-right"
                        type="number"
                        min={0}
                        step={1}
                        value={draftLimit}
                        onChange={(event) => setDraftLimit(event.target.value)}
                      />
                    ) : (
                      quota.monthly_limit.toLocaleString("pt-BR")
                    )}
                  </td>
                  <td className="p-4 text-right font-semibold">{quota.remaining_pages.toLocaleString("pt-BR")}</td>
                  <td className="p-4 text-right">
                    {editingId === quota.id ? (
                      <div className="flex justify-end gap-1">
                        <Button
                          type="button"
                          className="h-8 w-8 p-0"
                          title="Salvar limite"
                          disabled={savingId === quota.id}
                          onClick={() => saveQuota(quota)}
                        >
                          <Check className="h-4 w-4" />
                        </Button>
                        <Button type="button" variant="outline" className="h-8 w-8 p-0" title="Cancelar" onClick={cancelEdit}>
                          <X className="h-4 w-4" />
                        </Button>
                      </div>
                    ) : (
                      <Button type="button" variant="ghost" className="h-8 w-8 p-0" title="Editar limite mensal" onClick={() => startEdit(quota)}>
                        <Edit className="h-4 w-4 text-muted-foreground" />
                      </Button>
                    )}
                  </td>
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

function QuotaSignal({
  icon: Icon,
  label,
  value,
  detail,
}: {
  icon: ComponentType<{ className?: string }>;
  label: string;
  value: string;
  detail: string;
}) {
  return (
    <div className="rounded-md border border-slate-200 bg-slate-50 p-3">
      <div className="mb-2 flex items-center justify-between gap-3">
        <div className="text-[11px] font-bold uppercase text-muted-foreground">{label}</div>
        <Icon className="h-4 w-4 text-primary" />
      </div>
      <div className="text-lg font-bold">{value}</div>
      <div className="mt-1 text-xs text-muted-foreground">{detail}</div>
    </div>
  );
}

function QuotaTile({
  icon: Icon,
  label,
  value,
  detail,
  tone,
}: {
  icon: ComponentType<{ className?: string }>;
  label: string;
  value: number;
  detail: string;
  tone: "ok" | "warn" | "danger" | "info";
}) {
  const toneClass =
    tone === "ok"
      ? "border-emerald-200 bg-emerald-50 text-emerald-700"
      : tone === "warn"
      ? "border-amber-200 bg-amber-50 text-amber-700"
      : tone === "danger"
      ? "border-red-200 bg-red-50 text-red-700"
      : "border-blue-200 bg-blue-50 text-blue-700";

  return (
    <div className="border-b p-4 sm:border-r odd:sm:border-r">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div className="text-xs font-bold uppercase text-muted-foreground">{label}</div>
        <span className={`flex h-8 w-8 items-center justify-center rounded-md border ${toneClass}`}>
          <Icon className="h-4 w-4" />
        </span>
      </div>
      <div className="text-2xl font-bold">{value.toLocaleString("pt-BR")}</div>
      <div className="mt-1 text-xs leading-5 text-muted-foreground">{detail}</div>
    </div>
  );
}
