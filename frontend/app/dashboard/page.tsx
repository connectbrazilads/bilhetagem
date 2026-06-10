"use client";

import { useEffect, useState } from "react";
import { Activity, AlertTriangle, BarChart3, Check, FileText, Info, Leaf, Printer, Server, ShieldAlert, TrendingUp, Users, WalletCards, X } from "lucide-react";

import { ProtectedPage } from "@/components/protected-page";
import { Button, Surface } from "@/components/ui";
import { apiFetch, getCurrentRole, getCurrentUsername, type DashboardMetrics } from "@/lib/api";

type JobRow = {
  id: number;
  username: string;
  printer_name: string;
  document_name: string | null;
  pages: number;
  is_color: boolean;
  status: string;
  reason: string | null;
  submitted_at: string;
  cost?: number;
};

function MoneyLine({ cost, costPerPage }: { cost?: number; costPerPage?: number }) {
  if (typeof cost !== "number" && typeof costPerPage !== "number") return null;
  return (
    <span className="mt-0.5 block text-xs text-muted-foreground">
      {typeof cost === "number" ? `R$ ${cost.toFixed(2)}` : ""}
      {typeof cost === "number" && typeof costPerPage === "number" ? " | " : ""}
      {typeof costPerPage === "number" ? `R$ ${costPerPage.toFixed(2)}/pag.` : ""}
    </span>
  );
}

function Stat({ label, value, icon: Icon }: { label: string; value: number; icon: typeof FileText }) {
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

function HealthStat({
  label,
  value,
  detail,
  tone,
  icon: Icon,
}: {
  label: string;
  value: number;
  detail: string;
  tone: "ok" | "warn" | "danger" | "neutral";
  icon: typeof FileText;
}) {
  const tones = {
    ok: "border-emerald-100 bg-emerald-50/70 text-emerald-900",
    warn: "border-amber-100 bg-amber-50/80 text-amber-900",
    danger: "border-red-100 bg-red-50/80 text-red-900",
    neutral: "border-slate-200 bg-slate-50 text-slate-900",
  };
  const iconTones = {
    ok: "bg-emerald-100 text-emerald-700",
    warn: "bg-amber-100 text-amber-700",
    danger: "bg-red-100 text-red-700",
    neutral: "bg-slate-200 text-slate-700",
  };
  return (
    <Surface className={`p-4 ${tones[tone]}`}>
      <div className="flex items-center justify-between gap-3">
        <div>
          <div className="text-xs font-semibold uppercase opacity-75">{label}</div>
          <div className="mt-1 text-2xl font-bold">{value.toLocaleString("pt-BR")}</div>
          <div className="mt-0.5 text-xs opacity-75">{detail}</div>
        </div>
        <div className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-md ${iconTones[tone]}`}>
          <Icon className="h-4 w-4" />
        </div>
      </div>
    </Surface>
  );
}

function EcoStat({ label, value, detail }: { label: string; value: string; detail: string }) {
  return (
    <Surface className="border-emerald-100 bg-emerald-50/70 p-5">
      <div className="flex items-center justify-between">
        <span className="text-sm font-semibold text-emerald-900">{label}</span>
        <Leaf className="h-4 w-4 text-emerald-600" />
      </div>
      <div className="mt-3 text-3xl font-bold text-emerald-950">{value}</div>
      <div className="mt-1 text-xs text-emerald-700">{detail}</div>
    </Surface>
  );
}

export default function DashboardPage() {
  const [data, setData] = useState<DashboardMetrics | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [jobs, setJobs] = useState<JobRow[]>([]);
  const [username, setUsername] = useState<string | null>(null);
  const [role, setRole] = useState<string | null>(null);
  const [safeReleaseEnabled, setSafeReleaseEnabled] = useState(false);

  async function loadMetrics() {
    const token = localStorage.getItem("token");
    if (!token) return;
    apiFetch<DashboardMetrics>("/reports", token).then(setData).catch((err) => setError(err.message));
  }

  async function loadJobs() {
    const token = localStorage.getItem("token");
    if (!token) return;
    try {
      const rows = await apiFetch<JobRow[]>("/jobs", token);
      setJobs(rows);
      setUsername(getCurrentUsername(token));
      setRole(getCurrentRole(token));
    } catch {
      setJobs([]);
    }
  }

  async function loadSettings() {
    const token = localStorage.getItem("token");
    if (!token) return;
    try {
      const settings = await apiFetch<{ safe_release_enabled: boolean }>("/settings/operational", token);
      setSafeReleaseEnabled(settings.safe_release_enabled);
    } catch {
      setSafeReleaseEnabled(false);
    }
  }

  useEffect(() => {
    loadMetrics();
    loadJobs();
    loadSettings();

    const interval = setInterval(() => {
      loadJobs();
      loadMetrics();
      loadSettings();
    }, 15000);
    return () => clearInterval(interval);
  }, []);

  async function handleRelease(jobId: number) {
    const token = localStorage.getItem("token");
    if (!token) return;
    setError(null);
    try {
      await apiFetch(`/jobs/${jobId}/release`, token, { method: "POST" });
      await loadJobs();
      await loadMetrics();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao liberar trabalho");
    }
  }

  async function handleCancel(jobId: number) {
    const token = localStorage.getItem("token");
    if (!token) return;
    setError(null);
    try {
      await apiFetch(`/jobs/${jobId}/cancel`, token, { method: "POST" });
      await loadJobs();
      await loadMetrics();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao cancelar trabalho");
    }
  }

  const canOperateReleaseQueue = role === "admin" || role === "manager";
  const pendingJobs = jobs.filter(
    (job) => safeReleaseEnabled && job.status === "pending_release" && (canOperateReleaseQueue || job.username === username)
  );

  const totalMonth = data?.pages_month ?? 0;
  const health = data?.operational_health;

  return (
    <ProtectedPage>
      <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Dashboard</h1>
          <p className="mt-1 text-sm text-muted-foreground">Visao operacional de impressoes, consumo e filas.</p>
        </div>
        <Surface className="flex items-center gap-3 px-4 py-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-md bg-emerald-50 text-emerald-700">
            <TrendingUp className="h-4 w-4" />
          </div>
          <div>
            <div className="text-xs font-medium text-muted-foreground">Volume mensal</div>
            <div className="text-sm font-semibold">{totalMonth.toLocaleString("pt-BR")} paginas</div>
          </div>
        </Surface>
      </div>

      {error ? (
        <Surface className="mb-6 flex items-center gap-2 border-red-200 bg-red-50 p-4 text-sm text-red-800">
          <Info className="h-5 w-5 shrink-0 text-red-600" />
          <span>{error}</span>
        </Surface>
      ) : null}

      {pendingJobs.length > 0 ? (
        <Surface className="mb-6 border-primary/20 bg-primary/5 p-5">
          <div className="mb-4 flex items-center gap-2">
            <ShieldAlert className="h-5 w-5 text-primary" />
            <h2 className="text-lg font-semibold text-primary">Fila de Liberacao Segura</h2>
            <span className="rounded-full bg-primary/15 px-2.5 py-0.5 text-xs font-semibold text-primary">
              {pendingJobs.length} pendente(s)
            </span>
          </div>
          <div className="space-y-3">
            {pendingJobs.map((job) => (
              <div key={job.id} className="flex flex-wrap items-center justify-between gap-3 border-b border-primary/10 pb-3 last:border-0 last:pb-0">
                <div>
                  <div className="text-sm font-semibold text-foreground">{job.document_name ?? "Trabalho de impressao"}</div>
                  <div className="mt-0.5 text-xs text-muted-foreground">
                    Impressora: <span className="font-semibold text-foreground">{job.printer_name}</span> | Usuario:{" "}
                    <span className="font-semibold text-foreground">{job.username}</span> | Paginas:{" "}
                    <span className="font-semibold text-foreground">{job.pages}</span> | Tipo:{" "}
                    <span className={`font-semibold ${job.is_color ? "text-purple-600" : "text-foreground"}`}>
                      {job.is_color ? "Colorido" : "Preto e branco"}
                    </span>
                  </div>
                </div>
                <div className="flex gap-2">
                  <Button className="h-8 bg-green-600 px-3 text-xs text-white hover:bg-green-700" onClick={() => handleRelease(job.id)}>
                    <Check className="h-3.5 w-3.5" />
                    Liberar
                  </Button>
                  <Button variant="outline" className="h-8 border-red-200 px-3 text-xs text-red-600 hover:bg-red-50" onClick={() => handleCancel(job.id)}>
                    <X className="h-3.5 w-3.5" />
                    Cancelar
                  </Button>
                </div>
              </div>
            ))}
          </div>
        </Surface>
      ) : null}

      <div className="grid gap-4 md:grid-cols-4">
        <Stat label="Impressoes hoje" value={data?.prints_today ?? 0} icon={FileText} />
        <Stat label="Paginas hoje" value={data?.pages_today ?? 0} icon={Printer} />
        <Stat label="Impressoes no mes" value={data?.prints_month ?? 0} icon={Users} />
        <Stat label="Paginas no mes" value={data?.pages_month ?? 0} icon={WalletCards} />
      </div>

      {health ? (
        <div className="mt-4 grid gap-4 md:grid-cols-4">
          <HealthStat
            label="Agents online"
            value={health.agents_online}
            detail={`${health.agents_total.toLocaleString("pt-BR")} agent(s) cadastrados`}
            tone={health.agents_offline > 0 ? "warn" : "ok"}
            icon={Server}
          />
          <HealthStat
            label="Agents com alerta"
            value={health.agents_with_alerts}
            detail={`${health.agents_offline.toLocaleString("pt-BR")} offline agora`}
            tone={health.agents_with_alerts > 0 ? "danger" : "ok"}
            icon={AlertTriangle}
          />
          <HealthStat
            label="Filas sem vinculo"
            value={health.unbound_queues}
            detail={`${health.usb_queues.toLocaleString("pt-BR")} fila(s) USB detectadas`}
            tone={health.unbound_queues > 0 ? "warn" : "ok"}
            icon={Activity}
          />
          <HealthStat
            label="Monitoramento"
            value={health.printers_monitored}
            detail={`${health.printers_unmonitored.toLocaleString("pt-BR")} sem IP/SNMP, ${health.low_toner_printers.toLocaleString("pt-BR")} toner baixo`}
            tone={health.printers_unmonitored > 0 || health.low_toner_printers > 0 ? "warn" : "neutral"}
            icon={Printer}
          />
        </div>
      ) : null}

      {data?.eco_metrics ? (
        <div className="mt-4 grid gap-4 md:grid-cols-4">
          <EcoStat label="Paginas salvas" value={data.eco_metrics.pages_saved.toLocaleString("pt-BR")} detail="Bloqueios e cancelamentos" />
          <EcoStat label="Arvores salvas" value={data.eco_metrics.trees_saved.toFixed(4)} detail="Impacto florestal reduzido" />
          <EcoStat label="Agua preservada" value={`${data.eco_metrics.water_saved_l.toLocaleString("pt-BR")} L`} detail="Consumo industrial evitado" />
          <EcoStat
            label="CO2 evitado"
            value={data.eco_metrics.co2_saved_g >= 1000 ? `${(data.eco_metrics.co2_saved_g / 1000).toFixed(2)} kg` : `${data.eco_metrics.co2_saved_g.toFixed(0)} g`}
            detail="Gases estufa prevenidos"
          />
        </div>
      ) : null}

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <Surface className="p-5">
          <div className="mb-4 flex items-center gap-2">
            <BarChart3 className="h-4 w-4 text-primary" />
            <h2 className="text-sm font-semibold text-muted-foreground">Top usuarios</h2>
          </div>
          <div className="space-y-2">
            {(data?.top_users ?? []).map((item) => (
              <div key={item.username} className="flex items-center justify-between border-b py-2 text-sm last:border-0">
                <span className="font-medium">{item.username}</span>
                <span className="text-right">
                  <span className="font-medium text-foreground">{item.pages} pag.</span>
                  <MoneyLine cost={item.cost} costPerPage={item.cost_per_page} />
                </span>
              </div>
            ))}
          </div>
        </Surface>
        <Surface className="p-5">
          <div className="mb-4 flex items-center gap-2">
            <Printer className="h-4 w-4 text-primary" />
            <h2 className="text-sm font-semibold text-muted-foreground">Top impressoras</h2>
          </div>
          <div className="space-y-2">
            {(data?.top_printers ?? []).map((item) => (
              <div key={item.printer} className="flex items-center justify-between border-b py-2 text-sm last:border-0">
                <span className="font-medium">{item.printer}</span>
                <span className="text-right">
                  <span className="font-medium text-foreground">{item.pages} pag.</span>
                  <MoneyLine cost={item.cost} costPerPage={item.cost_per_page} />
                </span>
              </div>
            ))}
          </div>
        </Surface>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <Surface className="p-5">
          <h2 className="mb-4 text-sm font-semibold text-muted-foreground">Consumo por departamento</h2>
          {(data?.department_usage ?? []).map((item) => (
            <div key={item.department} className="mb-4 last:mb-0">
              <div className="mb-1 flex justify-between text-sm">
                <span className="font-medium">{item.department}</span>
                <span className="text-right">
                  <span className="font-medium text-foreground">{item.pages} pag.</span>
                  <MoneyLine cost={item.cost} costPerPage={item.cost_per_page} />
                </span>
              </div>
              <div className="h-2 overflow-hidden rounded bg-muted">
                <div className="h-full rounded bg-primary transition-all duration-500" style={{ width: `${Math.min(item.pages, 100)}%` }} />
              </div>
            </div>
          ))}
        </Surface>
        <Surface className="p-5">
          <h2 className="mb-4 text-sm font-semibold text-muted-foreground">Colorido x preto e branco</h2>
          {(data?.color_usage ?? []).map((item) => (
            <div key={item.type} className="flex items-center justify-between border-b py-2 text-sm last:border-0">
              <span className="font-medium">{item.type}</span>
              <span className="text-right">
                <span className="font-medium text-foreground">{item.pages} pag.</span>
                <MoneyLine cost={item.cost} costPerPage={item.cost_per_page} />
              </span>
            </div>
          ))}
        </Surface>
      </div>
    </ProtectedPage>
  );
}
