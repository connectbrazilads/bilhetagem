"use client";

import { useCallback, useEffect, useMemo, useState, type ComponentType } from "react";
import Link from "next/link";
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  ClipboardCheck,
  Download,
  FileText,
  HardDriveDownload,
  MonitorCog,
  Printer,
  RefreshCw,
  Router,
  Server,
  ShieldCheck,
  TerminalSquare,
  Usb,
  XCircle,
} from "lucide-react";

import { ProtectedPage } from "@/components/protected-page";
import { Badge, Button, Surface } from "@/components/ui";
import { apiFetch, type DashboardMetrics } from "@/lib/api";

type AgentRelease = {
  version: string;
  channel: string;
  published_at: string | null;
  checksums_url: string | null;
  checksums_sha256: string | null;
  signature_status: string;
  signature_summary: string;
  files: { kind: string; filename: string; signature_status: string | null }[];
};

type AgentRow = {
  id: number;
  computer_name: string | null;
  os_user: string | null;
  version: string | null;
  event_log_enabled: boolean | null;
  auto_update_enabled: boolean | null;
  local_admin: boolean | null;
  last_seen_at: string | null;
  is_online: boolean;
  health_alerts: { code: string; severity: string; message: string }[];
  aliases: {
    id: number;
    printer_id: number | null;
    queue_name: string;
    connection_type: string | null;
    ip_address: string | null;
    is_present: boolean;
  }[];
};

type PrinterRow = {
  id: number;
  name: string;
  is_active: boolean;
  ip_address: string | null;
  toner_level: number | null;
  toner_levels: Record<string, number> | null;
  serial_number: string | null;
  page_counter: number | null;
  aliases?: {
    id: number;
    printer_id: number | null;
    connection_type: string | null;
    is_present?: boolean;
  }[];
};

type JobRow = {
  id: number;
  username: string;
  printer_name: string;
  document_name: string | null;
  pages: number;
  status: string;
  submitted_at: string;
};

type AuthContext = {
  organization_name: string;
  organization_slug: string;
  organization_billing_status: "trial" | "active" | "past_due" | "suspended";
};

type ChecklistItem = {
  id: string;
  title: string;
  detail: string;
  status: "done" | "warn" | "pending";
  href?: string;
};

function formatDateTime(value: string | null) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  return new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeStyle: "short" }).format(date);
}

function releaseHasKind(release: AgentRelease | undefined, kind: "installer" | "msi" | "agent") {
  return Boolean(release?.files.some((file) => file.kind === kind || (kind === "msi" && file.filename.toLowerCase().endsWith(".msi"))));
}

function percent(done: number, total: number) {
  if (!total) return 0;
  return Math.round((done / total) * 100);
}

function statusTone(status: ChecklistItem["status"]) {
  if (status === "done") return "border-emerald-200 bg-emerald-50 text-emerald-700";
  if (status === "warn") return "border-amber-200 bg-amber-50 text-amber-700";
  return "border-slate-200 bg-slate-100 text-slate-700";
}

function statusLabel(status: ChecklistItem["status"]) {
  if (status === "done") return "OK";
  if (status === "warn") return "Atencao";
  return "Pendente";
}

function statusIcon(status: ChecklistItem["status"]) {
  if (status === "done") return <CheckCircle2 className="h-4 w-4" />;
  if (status === "warn") return <AlertTriangle className="h-4 w-4" />;
  return <XCircle className="h-4 w-4" />;
}

export default function DeploymentPage() {
  const [metrics, setMetrics] = useState<DashboardMetrics | null>(null);
  const [releases, setReleases] = useState<AgentRelease[]>([]);
  const [agents, setAgents] = useState<AgentRow[]>([]);
  const [printers, setPrinters] = useState<PrinterRow[]>([]);
  const [jobs, setJobs] = useState<JobRow[]>([]);
  const [context, setContext] = useState<AuthContext | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    const token = localStorage.getItem("token");
    if (!token) return;
    setLoading(true);
    setError(null);
    try {
      const [reportsData, releasesData, agentsData, printersData, jobsData, authData] = await Promise.all([
        apiFetch<DashboardMetrics>("/reports", token),
        apiFetch<AgentRelease[]>("/agent/releases", token).catch(() => []),
        apiFetch<AgentRow[]>("/agent/agents", token).catch(() => []),
        apiFetch<PrinterRow[]>("/printers", token).catch(() => []),
        apiFetch<JobRow[]>("/jobs", token).catch(() => []),
        apiFetch<AuthContext>("/auth/me", token).catch(() => null),
      ]);
      setMetrics(reportsData);
      setReleases(releasesData);
      setAgents(agentsData);
      setPrinters(printersData);
      setJobs(jobsData);
      setContext(authData);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao carregar diagnostico de implantacao.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const interval = window.setInterval(load, 15000);
    return () => window.clearInterval(interval);
  }, [load]);

  const latest = releases[0];
  const health = metrics?.operational_health ?? null;
  const latestJob = jobs[0] ?? null;
  const onlineAgents = agents.filter((agent) => agent.is_online);
  const agentsWithAdmin = agents.filter((agent) => agent.local_admin === true);
  const agentsWithEventLog = agents.filter((agent) => agent.event_log_enabled === true);
  const agentsWithAutoUpdate = agents.filter((agent) => agent.auto_update_enabled === true);
  const presentQueues = agents.flatMap((agent) => agent.aliases.filter((alias) => alias.is_present));
  const boundQueues = presentQueues.filter((alias) => alias.printer_id);
  const usbQueues = presentQueues.filter((alias) => alias.connection_type === "usb");
  const networkQueues = presentQueues.filter((alias) => alias.connection_type === "network" || alias.ip_address);
  const monitoredPrinters = printers.filter(
    (printer) =>
      printer.ip_address &&
      (printer.serial_number || printer.page_counter !== null || printer.toner_level !== null || Object.keys(printer.toner_levels ?? {}).length > 0)
  );
  const hasDuplicateRisk = Boolean(
    (health?.duplicate_queue_aliases ?? 0) > 0 ||
      (health?.generic_queue_aliases ?? 0) > 0 ||
      (health?.hardware_identity_conflicts ?? 0) > 0
  );

  const checklist = useMemo<ChecklistItem[]>(() => {
    const hasExe = releaseHasKind(latest, "installer");
    const hasMsi = releaseHasKind(latest, "msi");
    const hasAgent = releaseHasKind(latest, "agent");
    return [
      {
        id: "org",
        title: "Empresa pronta",
        detail: context
          ? `${context.organization_name} (${context.organization_slug}) - ${context.organization_billing_status}`
          : "Login valido, aguardando contexto da empresa.",
        status: context?.organization_billing_status === "suspended" ? "warn" : "done",
        href: "/organizations",
      },
      {
        id: "release",
        title: "Release oficial do agent",
        detail: latest
          ? `v${latest.version} com ${[hasExe ? "EXE" : null, hasMsi ? "MSI" : null, latest.checksums_url ? "SHA256" : null].filter(Boolean).join(" + ") || "artefatos incompletos"}`
          : "Nenhuma release publicada no manifest.",
        status: latest && hasAgent && hasExe && latest.checksums_url ? "done" : latest && (hasExe || hasMsi) ? "warn" : "pending",
        href: "/downloads",
      },
      {
        id: "signature",
        title: "Assinatura e distribuicao",
        detail: latest ? latest.signature_summary : "Publique uma release para validar assinatura e checksums.",
        status: latest?.signature_status === "signed" ? "done" : latest ? "warn" : "pending",
        href: "/downloads",
      },
      {
        id: "agent",
        title: "Agent instalado",
        detail: `${agents.length.toLocaleString("pt-BR")} PC(s) cadastrado(s), ${onlineAgents.length.toLocaleString("pt-BR")} online.`,
        status: onlineAgents.length > 0 ? "done" : agents.length > 0 ? "warn" : "pending",
        href: "/agents",
      },
      {
        id: "capture",
        title: "Captura Windows ativa",
        detail: `${agentsWithEventLog.length.toLocaleString("pt-BR")} agent(s) com Event Log, ${agentsWithAdmin.length.toLocaleString("pt-BR")} com admin local.`,
        status: agentsWithEventLog.length > 0 && agentsWithAdmin.length > 0 ? "done" : onlineAgents.length > 0 ? "warn" : "pending",
        href: "/agents",
      },
      {
        id: "queues",
        title: "Filas detectadas",
        detail: `${presentQueues.length.toLocaleString("pt-BR")} fila(s), ${boundQueues.length.toLocaleString("pt-BR")} vinculada(s) a impressora fisica.`,
        status: presentQueues.length > 0 && boundQueues.length > 0 ? "done" : presentQueues.length > 0 ? "warn" : "pending",
        href: "/agents",
      },
      {
        id: "snmp",
        title: "SNMP validado quando houver rede",
        detail: `${monitoredPrinters.length.toLocaleString("pt-BR")} impressora(s) com telemetria; ${usbQueues.length.toLocaleString("pt-BR")} fila(s) USB sem SNMP.`,
        status: monitoredPrinters.length > 0 || usbQueues.length > 0 ? "done" : printers.length > 0 ? "warn" : "pending",
        href: "/printers",
      },
      {
        id: "first-job",
        title: "Primeira impressao capturada",
        detail: latestJob
          ? `${latestJob.username} imprimiu ${latestJob.pages} pag. em ${latestJob.printer_name} - ${formatDateTime(latestJob.submitted_at)}`
          : "Nenhum job registrado ainda.",
        status: latestJob ? "done" : "pending",
        href: "/reports",
      },
      {
        id: "duplicates",
        title: "Risco de duplicidade controlado",
        detail: health
          ? `${health.duplicate_queue_aliases} fila(s) duplicada(s), ${health.generic_queue_aliases} nome(s) generico(s), ${health.hardware_identity_conflicts} conflito(s) fisico(s).`
          : "Aguardando saude operacional.",
        status: hasDuplicateRisk ? "warn" : "done",
        href: "/printers",
      },
      {
        id: "autoupdate",
        title: "Auto-update ligado",
        detail: `${agentsWithAutoUpdate.length.toLocaleString("pt-BR")} de ${agents.length.toLocaleString("pt-BR")} agent(s) com atualizacao automatica.`,
        status: agents.length === 0 ? "pending" : agentsWithAutoUpdate.length === agents.length ? "done" : "warn",
        href: "/agents",
      },
    ];
  }, [
    agents.length,
    agentsWithAdmin.length,
    agentsWithAutoUpdate.length,
    agentsWithEventLog.length,
    boundQueues.length,
    context,
    hasDuplicateRisk,
    health,
    latest,
    latestJob,
    monitoredPrinters.length,
    onlineAgents.length,
    presentQueues.length,
    printers.length,
    usbQueues.length,
  ]);

  const doneCount = checklist.filter((item) => item.status === "done").length;
  const warnCount = checklist.filter((item) => item.status === "warn").length;
  const progress = percent(doneCount, checklist.length);
  const readyForPilot = progress >= 80 && warnCount <= 2 && jobs.length > 0 && onlineAgents.length > 0;

  return (
    <ProtectedPage>
      <div className="mb-6 grid gap-4 xl:grid-cols-[1.5fr_0.9fr]">
        <Surface className="overflow-hidden border-slate-200 bg-slate-950 p-0 text-white">
          <div className="grid gap-6 p-6 md:grid-cols-[1fr_auto] md:p-8">
            <div>
              <Badge className="border-white/15 bg-white/10 text-white">
                <ClipboardCheck className="h-3.5 w-3.5" />
                Piloto real
              </Badge>
              <h1 className="mt-4 text-3xl font-bold md:text-4xl">Implantacao pronta para teste em empresa</h1>
              <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-300">
                Valide release, agent, filas, SNMP, usuarios, relatorios e riscos antes de colocar em operacao real.
              </p>
              <div className="mt-5 flex flex-wrap gap-2">
                <Button asChild className="bg-white text-slate-950 hover:bg-slate-100 hover:text-slate-950">
                  <Link href="/downloads">
                    <HardDriveDownload className="h-4 w-4" />
                    Baixar agent
                  </Link>
                </Button>
                <Button asChild variant="outline" className="border-white/20 bg-white/10 text-white hover:bg-white/15 hover:text-white">
                  <Link href="/agents">
                    <MonitorCog className="h-4 w-4" />
                    Ver agents
                  </Link>
                </Button>
              </div>
            </div>
            <div className="min-w-[220px] rounded-lg border border-white/10 bg-white/10 p-5">
              <div className="text-xs font-semibold uppercase text-slate-300">Prontidao</div>
              <div className="mt-2 text-5xl font-bold">{progress}%</div>
              <div className="mt-3 h-2 overflow-hidden rounded-full bg-white/15">
                <div className="h-full rounded-full bg-emerald-400 transition-all" style={{ width: `${progress}%` }} />
              </div>
              <div className="mt-3 text-sm font-semibold">{readyForPilot ? "Liberado para piloto controlado" : "Ainda precisa validar pontos"}</div>
              <div className="mt-1 text-xs text-slate-300">{doneCount} ok, {warnCount} atencao, {checklist.length - doneCount - warnCount} pendente(s)</div>
            </div>
          </div>
        </Surface>

        <Surface className="p-5">
          <div className="mb-4 flex items-center justify-between gap-3">
            <div>
              <h2 className="text-sm font-bold">Status da release</h2>
              <p className="text-xs text-muted-foreground">Base para instalacao em campo.</p>
            </div>
            <Button variant="outline" onClick={load} disabled={loading}>
              <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
              Atualizar
            </Button>
          </div>
          {error ? <div className="mb-3 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</div> : null}
          <div className="grid gap-3">
            <ReleaseLine icon={Download} label="Versao publicada" value={latest?.version ?? "Sem release"} />
            <ReleaseLine icon={ShieldCheck} label="Assinatura" value={latest ? latest.signature_summary : "Aguardando manifest"} />
            <ReleaseLine icon={TerminalSquare} label="Instaladores" value={`${releaseHasKind(latest, "installer") ? "EXE" : "-"} / ${releaseHasKind(latest, "msi") ? "MSI" : "-"}`} />
            <ReleaseLine icon={Server} label="Checksums" value={latest?.checksums_url ? "SHA256 publicado" : "Nao publicado"} />
          </div>
        </Surface>
      </div>

      <div className="mb-6 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <PilotMetric icon={MonitorCog} label="Agents online" value={onlineAgents.length} detail={`${agents.length} cadastrado(s)`} tone={onlineAgents.length > 0 ? "ok" : "warn"} />
        <PilotMetric icon={Printer} label="Filas vinculadas" value={boundQueues.length} detail={`${presentQueues.length} detectada(s)`} tone={boundQueues.length > 0 ? "ok" : "warn"} />
        <PilotMetric icon={Router} label="SNMP / rede" value={monitoredPrinters.length} detail={`${networkQueues.length} fila(s) de rede`} tone={monitoredPrinters.length > 0 ? "ok" : "neutral"} />
        <PilotMetric icon={FileText} label="Jobs capturados" value={jobs.length} detail={latestJob ? formatDateTime(latestJob.submitted_at) : "Sem impressao"} tone={jobs.length > 0 ? "ok" : "warn"} />
      </div>

      <div className="grid gap-6 xl:grid-cols-[1fr_420px]">
        <Surface className="overflow-hidden">
          <div className="border-b bg-white/70 p-5">
            <h2 className="text-lg font-bold">Checklist do piloto</h2>
            <p className="text-sm text-muted-foreground">O objetivo e chegar acima de 80% sem pendencias criticas antes do teste real.</p>
          </div>
          <div className="divide-y">
            {checklist.map((item) => (
              <div key={item.id} className="grid gap-3 p-4 md:grid-cols-[auto_1fr_auto] md:items-center">
                <div className={`flex h-10 w-10 items-center justify-center rounded-md border ${statusTone(item.status)}`}>
                  {statusIcon(item.status)}
                </div>
                <div>
                  <div className="font-semibold">{item.title}</div>
                  <div className="mt-0.5 text-sm text-muted-foreground">{item.detail}</div>
                </div>
                <div className="flex items-center gap-2">
                  <Badge className={statusTone(item.status)}>{statusLabel(item.status)}</Badge>
                  {item.href ? (
                    <Button asChild variant="ghost" className="h-8 px-2">
                      <Link href={item.href} title={`Abrir ${item.title}`}>
                        <ArrowRight className="h-4 w-4" />
                      </Link>
                    </Button>
                  ) : null}
                </div>
              </div>
            ))}
          </div>
        </Surface>

        <div className="grid gap-4">
          <Surface className="p-5">
            <div className="mb-4 flex items-center gap-2">
              <Activity className="h-4 w-4 text-primary" />
              <h2 className="text-sm font-bold">Roteiro do teste real</h2>
            </div>
            <div className="grid gap-3">
              <TestStep number="1" title="Instalar em 2 PCs" detail="Use o comando silencioso da tela Downloads na mesma empresa." href="/downloads" />
              <TestStep number="2" title="Imprimir na mesma Konica" detail="Mesmo com nomes diferentes no Windows, o alias deve cair na mesma impressora fisica." href="/agents" />
              <TestStep number="3" title="Validar USB" detail="Impressora USB deve bilhetar; toner e contador SNMP ficam indisponiveis sem IP." href="/printers" />
              <TestStep number="4" title="Gerar relatorio" detail="Confirme usuario, impressora, documento, paginas, cor e custo no PDF/Excel." href="/reports" />
            </div>
          </Surface>

          <Surface className="p-5">
            <div className="mb-4 flex items-center gap-2">
              <AlertTriangle className="h-4 w-4 text-amber-600" />
              <h2 className="text-sm font-bold">Pontos de atencao</h2>
            </div>
            <div className="space-y-3 text-sm">
              <AttentionLine
                icon={Usb}
                title="USB"
                detail="Captura trabalhos, mas nao entrega SNMP/toner sem IP de rede."
                active={usbQueues.length > 0}
              />
              <AttentionLine
                icon={Printer}
                title="Duplicidade"
                detail="Se aparecer nome generico ou conflito fisico, vincule/mescle antes de fechar relatorio."
                active={hasDuplicateRisk}
              />
              <AttentionLine
                icon={ShieldCheck}
                title="Assinatura"
                detail="Para cliente externo, ainda falta certificado real para reduzir alerta do Windows."
                active={latest?.signature_status !== "signed"}
              />
            </div>
          </Surface>
        </div>
      </div>
    </ProtectedPage>
  );
}

function PilotMetric({
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
  tone: "ok" | "warn" | "neutral";
}) {
  const toneClass =
    tone === "ok"
      ? "border-emerald-200 bg-emerald-50 text-emerald-700"
      : tone === "warn"
      ? "border-amber-200 bg-amber-50 text-amber-700"
      : "border-blue-200 bg-blue-50 text-blue-700";
  return (
    <Surface className="p-5">
      <div className="flex items-center justify-between gap-3">
        <div>
          <div className="text-sm font-medium text-muted-foreground">{label}</div>
          <div className="mt-2 text-3xl font-bold">{value.toLocaleString("pt-BR")}</div>
          <div className="mt-1 text-xs text-muted-foreground">{detail}</div>
        </div>
        <div className={`flex h-11 w-11 items-center justify-center rounded-md border ${toneClass}`}>
          <Icon className="h-5 w-5" />
        </div>
      </div>
    </Surface>
  );
}

function ReleaseLine({ icon: Icon, label, value }: { icon: ComponentType<{ className?: string }>; label: string; value: string }) {
  return (
    <div className="flex items-center gap-3 rounded-md border bg-muted/25 p-3">
      <div className="flex h-9 w-9 items-center justify-center rounded-md bg-primary/10 text-primary">
        <Icon className="h-4 w-4" />
      </div>
      <div className="min-w-0">
        <div className="text-xs font-semibold uppercase text-muted-foreground">{label}</div>
        <div className="truncate text-sm font-semibold" title={value}>
          {value}
        </div>
      </div>
    </div>
  );
}

function TestStep({ number, title, detail, href }: { number: string; title: string; detail: string; href: string }) {
  return (
    <Link href={href} className="group grid grid-cols-[34px_1fr_auto] items-center gap-3 rounded-md border bg-muted/20 p-3 transition-colors hover:border-primary/30 hover:bg-primary/5">
      <div className="flex h-8 w-8 items-center justify-center rounded-md bg-slate-950 text-xs font-bold text-white">{number}</div>
      <div>
        <div className="text-sm font-bold">{title}</div>
        <div className="text-xs text-muted-foreground">{detail}</div>
      </div>
      <ArrowRight className="h-4 w-4 text-muted-foreground transition-transform group-hover:translate-x-0.5 group-hover:text-primary" />
    </Link>
  );
}

function AttentionLine({
  icon: Icon,
  title,
  detail,
  active,
}: {
  icon: ComponentType<{ className?: string }>;
  title: string;
  detail: string;
  active: boolean;
}) {
  return (
    <div className={`rounded-md border p-3 ${active ? "border-amber-200 bg-amber-50 text-amber-900" : "bg-muted/20"}`}>
      <div className="flex items-start gap-3">
        <Icon className={`mt-0.5 h-4 w-4 shrink-0 ${active ? "text-amber-700" : "text-muted-foreground"}`} />
        <div>
          <div className="font-semibold">{title}</div>
          <div className="mt-0.5 text-xs opacity-80">{detail}</div>
        </div>
      </div>
    </div>
  );
}
