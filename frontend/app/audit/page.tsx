"use client";

import { useCallback, useEffect, useMemo, useState, type ComponentType } from "react";
import { Activity, AlertTriangle, Download, FileDown, Filter, History, RefreshCcw, ServerCog, ShieldCheck, UserCheck } from "lucide-react";

import { ProtectedPage } from "@/components/protected-page";
import { Button, Input, Surface } from "@/components/ui";
import { API_URL, apiFetch } from "@/lib/api";

type AuditLogRow = {
  id: number;
  actor_user_id: number | null;
  actor_username: string | null;
  action: string;
  entity: string;
  entity_id: number | null;
  metadata: Record<string, unknown>;
  created_at: string;
};

type AuditFacets = {
  actions: string[];
  entities: string[];
};

const ACTION_LABELS: Record<string, string> = {
  agent_queue_action_cancelled: "Acao remota cancelada",
  agent_queue_action_created: "Acao remota criada",
  agent_queue_action_dispatched: "Acao remota enviada",
  agent_queue_action_finished: "Acao remota finalizada",
  agent_release_checksums_downloaded: "Checksums do agent baixados",
  agent_release_downloaded: "Release do agent baixada",
  audit_logs_exported: "Auditoria exportada",
  department_created: "Departamento criado",
  department_deleted: "Departamento excluido",
  department_updated: "Departamento atualizado",
  ldap_settings_updated: "LDAP atualizado",
  ldap_sync_performed: "LDAP sincronizado",
  monthly_closing_due_email_failed: "Falha no envio mensal",
  monthly_closing_due_email_sent: "Fechamento mensal enviado",
  monthly_closing_email_sent: "Fechamento mensal enviado manualmente",
  monthly_closing_exported: "Fechamento mensal exportado",
  monthly_closing_generated: "Fechamento mensal gerado",
  monthly_report_email_settings_updated: "Envio mensal atualizado",
  pending_jobs_auto_released: "Fila liberada automaticamente",
  policy_created: "Politica criada",
  policy_deleted: "Politica excluida",
  policy_reordered: "Politicas reordenadas",
  policy_updated: "Politica atualizada",
  print_job_authorized: "Impressao autorizada",
  print_job_blocked: "Impressao bloqueada",
  print_job_cancelled: "Impressao cancelada",
  print_job_released: "Impressao liberada",
  organization_created: "Empresa criada",
  organization_updated: "Empresa atualizada",
  printer_created: "Impressora criada",
  printer_deleted: "Impressora excluida",
  printer_alias_bound: "Fila vinculada",
  printer_alias_unbound: "Fila desvinculada",
  printer_merged: "Impressora mesclada",
  printer_updated: "Impressora atualizada",
  quota_updated: "Cota atualizada",
  report_exported: "Relatorio exportado",
  settings_updated: "Configuracoes atualizadas",
  user_created: "Usuario criado",
  user_deleted: "Usuario excluido",
  user_updated: "Usuario atualizado",
  web_print_confirmed: "Web Print confirmado",
};

const ENTITY_LABELS: Record<string, string> = {
  agent_queue_actions: "Acoes remotas",
  agent_releases: "Releases do agent",
  audit_logs: "Auditoria",
  departments: "Departamentos",
  organizations: "Empresas",
  print_jobs: "Impressoes",
  print_policies: "Politicas",
  printers: "Impressoras",
  quotas: "Cotas",
  reports: "Relatorios",
  settings: "Configuracoes",
  users: "Usuarios",
};

const FIELD_LABELS: Record<string, string> = {
  action_type: "Tipo da acao",
  agent: "Agent",
  agent_id: "ID do agent",
  agent_uid: "UID do agent",
  attachments: "Anexos",
  billing_plan: "Plano",
  billing_status: "Status comercial",
  billable_jobs: "Trabalhos cobraveis",
  blocked_cost: "Custo bloqueado",
  blocked_jobs: "Trabalhos bloqueados",
  blocked_pages: "Paginas bloqueadas",
  bulk: "Em lote",
  color_pages: "Paginas coloridas",
  computer_name: "Computador",
  contracted_printer_limit: "Limite contratado",
  deleted_jobs: "Historico removido",
  detached_queue_actions: "Acoes remotas desvinculadas",
  department_id: "Departamento",
  department_name: "Departamento",
  driver_name: "Driver",
  file_count: "Arquivos",
  filename: "Arquivo",
  full_name: "Nome",
  ip_address: "Endereco IP",
  is_active: "Ativo",
  kind: "Tipo de arquivo",
  limit: "Limite",
  mono_pages: "Paginas P&B",
  monthly_balance: "Saldo mensal",
  monthly_limit: "Limite mensal",
  month: "Mes",
  password: "Senha",
  pending_cost: "Custo pendente",
  pending_jobs: "Trabalhos pendentes",
  period: "Periodo",
  port_name: "Porta",
  previous_dispatched_at: "Envio anterior",
  previous_status: "Status anterior",
  printer_id: "Impressora",
  queue_name: "Fila",
  redispatch: "Reenvio",
  result_message: "Resultado",
  role: "Perfil",
  rows: "Linhas exportadas",
  sha256: "SHA256",
  status: "Status",
  total_matching_rows: "Registros encontrados",
  total_cost: "Custo total",
  total_jobs: "Trabalhos totais",
  total_pages: "Paginas totais",
  target_organization_id: "Empresa alvo",
  target_organization_name: "Nome da empresa alvo",
  target_organization_slug: "Slug da empresa alvo",
  truncated: "Exportacao truncada",
  version: "Versao",
  year: "Ano",
};

export default function AuditPage() {
  const [logs, setLogs] = useState<AuditLogRow[]>([]);
  const [facets, setFacets] = useState<AuditFacets>({ actions: [], entities: [] });
  const [action, setAction] = useState("");
  const [entity, setEntity] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [error, setError] = useState<string | null>(null);

  const buildParams = useCallback((limit = "200") => {
    const params = new URLSearchParams({ limit });
    if (action.trim()) params.set("action", action.trim());
    if (entity.trim()) params.set("entity", entity.trim());
    if (dateFrom) params.set("date_from", `${dateFrom}T00:00:00`);
    if (dateTo) params.set("date_to", `${dateTo}T23:59:59`);
    return params;
  }, [action, dateFrom, dateTo, entity]);

  const load = useCallback(async () => {
    const token = localStorage.getItem("token");
    if (!token) return;
    setError(null);
    const params = buildParams();
    try {
      await apiFetch<AuditLogRow[]>(`/audit-logs?${params.toString()}`, token).then(setLogs);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao carregar auditoria");
      setLogs([]);
    }
  }, [buildParams]);

  const loadFacets = useCallback(async () => {
    const token = localStorage.getItem("token");
    if (!token) return;
    try {
      const data = await apiFetch<AuditFacets>("/audit-logs/facets", token);
      setFacets(data);
    } catch {
      setFacets({ actions: [], entities: [] });
    }
  }, []);

  async function exportCsv() {
    const token = localStorage.getItem("token");
    if (!token) return;
    setError(null);
    const params = buildParams("5000");
    try {
      await downloadBlob(`/audit-logs/export?${params.toString()}`, buildAuditFilename(dateFrom, dateTo), token);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao exportar auditoria");
    }
  }

  async function downloadBlob(path: string, filename: string, token: string) {
    const response = await fetch(`${API_URL}${path}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!response.ok) {
      const detail = await response.text().catch(() => "");
      throw new Error(`Falha ao baixar ${filename}: ${readError({ message: detail }) || `HTTP ${response.status}`}`);
    }
    const blob = await response.blob();
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    link.click();
    window.URL.revokeObjectURL(url);
  }

  useEffect(() => {
    loadFacets();
    load();
  }, [load, loadFacets]);

  const summary = useMemo(() => {
    const actors = new Set(logs.map((log) => log.actor_username || "sistema"));
    const entities = new Set(logs.map((log) => log.entity));
    return {
      total: logs.length,
      actors: actors.size,
      entities: entities.size,
      critical: logs.filter((log) => isCriticalAuditAction(log.action)).length,
      queueActions: logs.filter((log) => log.action.startsWith("agent_queue_action_")).length,
      exports: logs.filter((log) => log.action.endsWith("_exported")).length,
      settings: logs.filter((log) => log.entity === "settings" || log.action.includes("settings")).length,
      jobs: logs.filter((log) => log.entity === "print_jobs").length,
      system: logs.filter((log) => !log.actor_username).length,
    };
  }, [logs]);
  const criticalPercent = summary.total ? Math.round((summary.critical / summary.total) * 100) : 0;

  return (
    <ProtectedPage>
      <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Auditoria</h1>
          <p className="mt-1 text-sm text-muted-foreground">Acompanhe alteracoes administrativas e eventos operacionais por empresa.</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={exportCsv}>
            <Download className="h-4 w-4" />
            CSV
          </Button>
          <Button variant="outline" onClick={load}>
            <RefreshCcw className="h-4 w-4" />
            Atualizar
          </Button>
        </div>
      </div>

      <Surface className="mb-6 overflow-hidden">
        <div className="grid gap-0 lg:grid-cols-[1.15fr_0.85fr]">
          <div className="border-b p-5 lg:border-b-0 lg:border-r">
            <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
              <div>
                <div className="text-xs font-bold uppercase text-muted-foreground">Centro de rastreabilidade</div>
                <div className="mt-1 text-xl font-bold">Auditoria administrativa</div>
              </div>
              <span className={`inline-flex rounded-full border px-2.5 py-1 text-xs font-bold ${summary.critical ? "border-amber-200 bg-amber-50 text-amber-700" : "border-emerald-200 bg-emerald-50 text-emerald-700"}`}>
                {summary.critical ? "Eventos sensiveis" : "Sem alerta no filtro"}
              </span>
            </div>
            <div className="mb-3 flex flex-wrap items-end gap-3">
              <div className="text-4xl font-bold">{criticalPercent}%</div>
              <div className="pb-1 text-sm text-muted-foreground">
                {summary.critical.toLocaleString("pt-BR")} de {summary.total.toLocaleString("pt-BR")} evento(s) sensiveis no filtro
              </div>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-slate-100">
              <div className={`h-full rounded-full ${summary.critical ? "bg-amber-500" : "bg-emerald-500"}`} style={{ width: `${criticalPercent}%` }} />
            </div>
            <div className="mt-4 grid gap-2 sm:grid-cols-3">
              <AuditSignal icon={History} label="Eventos" value={summary.total.toLocaleString("pt-BR")} detail="Dentro do filtro atual" />
              <AuditSignal icon={UserCheck} label="Atores" value={summary.actors.toLocaleString("pt-BR")} detail={`${summary.system} evento(s) do sistema`} />
              <AuditSignal icon={ShieldCheck} label="Entidades" value={summary.entities.toLocaleString("pt-BR")} detail="Areas afetadas" />
            </div>
          </div>
          <div className="grid gap-0 sm:grid-cols-2">
            <AuditTile icon={AlertTriangle} label="Criticos" value={summary.critical} detail="Mudancas sensiveis e falhas" tone={summary.critical ? "warn" : "ok"} />
            <AuditTile icon={ServerCog} label="Acoes remotas" value={summary.queueActions} detail="Criacao, restauracao e remocao de filas" tone={summary.queueActions ? "info" : "muted"} />
            <AuditTile icon={FileDown} label="Exportacoes" value={summary.exports} detail="Relatorios, fechamentos e auditoria" tone={summary.exports ? "info" : "muted"} />
            <AuditTile icon={Activity} label="Configuracoes" value={summary.settings} detail="Alteracoes de parametros e integracoes" tone={summary.settings ? "warn" : "muted"} />
          </div>
        </div>
      </Surface>

      <Surface className="mb-4 p-4">
        <div className="grid gap-3 md:grid-cols-[1fr_1fr_160px_160px_auto]">
          <select
            className="h-9 rounded-md border bg-white px-3 text-sm outline-none focus-visible:border-primary focus-visible:ring-2 focus-visible:ring-ring/20"
            value={action}
            onChange={(event) => setAction(event.target.value)}
          >
            <option value="">Todas as acoes</option>
            {facets.actions.map((item) => (
              <option key={item} value={item}>
                {auditActionLabel(item)}
              </option>
            ))}
          </select>
          <select
            className="h-9 rounded-md border bg-white px-3 text-sm outline-none focus-visible:border-primary focus-visible:ring-2 focus-visible:ring-ring/20"
            value={entity}
            onChange={(event) => setEntity(event.target.value)}
          >
            <option value="">Todas as entidades</option>
            {facets.entities.map((item) => (
              <option key={item} value={item}>
                {entityLabel(item)}
              </option>
            ))}
          </select>
          <Input type="date" value={dateFrom} onChange={(event) => setDateFrom(event.target.value)} />
          <Input type="date" value={dateTo} onChange={(event) => setDateTo(event.target.value)} />
          <Button onClick={load}>
            <Filter className="h-4 w-4" />
            Filtrar
          </Button>
        </div>
      </Surface>

      {error ? <Surface className="mb-4 border-red-200 bg-red-50 p-3 text-sm text-red-800">{error}</Surface> : null}

      <Surface className="overflow-hidden">
        <div className="border-b bg-muted/30 p-4 text-sm font-semibold">
          Eventos recentes <span className="text-muted-foreground">({logs.length})</span>
        </div>
        {logs.length === 0 ? (
          <div className="p-8 text-center text-sm text-muted-foreground">Nenhum evento de auditoria encontrado.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-muted/80 text-left text-xs uppercase tracking-wide text-muted-foreground">
                <tr>
                  <th className="p-4">Data</th>
                  <th className="p-4">Ator</th>
                  <th className="p-4">Acao</th>
                  <th className="p-4">Entidade</th>
                  <th className="p-4">Detalhes</th>
                </tr>
              </thead>
              <tbody>
                {logs.map((log) => (
                  <tr key={log.id} className="border-t bg-white transition-colors hover:bg-muted/30">
                    <td className="whitespace-nowrap p-4 text-muted-foreground">{new Date(log.created_at).toLocaleString("pt-BR")}</td>
                    <td className="p-4 font-medium">{log.actor_username || "Sistema"}</td>
                    <td className="p-4">
                      <span className={`inline-flex rounded-full border px-2 py-0.5 text-xs font-semibold ${auditActionClass(log.action, log.metadata)}`} title={log.action}>
                        {auditActionLabel(log.action)}
                      </span>
                    </td>
                    <td className="p-4">
                      <div className="font-medium" title={log.entity}>
                        {entityLabel(log.entity)}
                      </div>
                      <div className="text-xs text-muted-foreground">{log.entity_id ? `#${log.entity_id}` : "-"}</div>
                    </td>
                    <td className="min-w-[260px] p-4 font-mono text-xs text-muted-foreground">
                      {formatMetadata(log.metadata)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Surface>
    </ProtectedPage>
  );
}

function AuditSignal({
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

function AuditTile({
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
  tone: "ok" | "warn" | "info" | "muted";
}) {
  const toneClass =
    tone === "ok"
      ? "border-emerald-200 bg-emerald-50 text-emerald-700"
      : tone === "warn"
      ? "border-amber-200 bg-amber-50 text-amber-700"
      : tone === "info"
      ? "border-blue-200 bg-blue-50 text-blue-700"
      : "border-slate-200 bg-slate-50 text-slate-700";
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

function formatMetadata(metadata: Record<string, unknown>) {
  const entries = Object.entries(metadata);
  if (!entries.length) return "-";
  const parts: string[] = [];
  if (isPlainRecord(metadata.changes)) {
    parts.push(formatChanges(metadata.changes));
  }
  parts.push(
    ...entries
      .filter(([key]) => key !== "changes")
      .map(([key, value]) => `${fieldLabel(key)}: ${formatMetadataValue(value)}`)
  );
  return parts.filter(Boolean).join(" | ");
}

function formatMetadataValue(value: unknown): string {
  if (value === null || value === undefined) return "-";
  if (typeof value === "boolean") return value ? "Sim" : "Nao";
  if (typeof value === "number") return value.toLocaleString("pt-BR");
  if (Array.isArray(value)) return value.map(formatMetadataValue).join(", ");
  if (typeof value === "object") {
    return JSON.stringify(value);
  }
  return String(value);
}

function formatChanges(changes: Record<string, unknown>) {
  return Object.entries(changes)
    .map(([key, value]) => {
      if (isPlainRecord(value) && ("before" in value || "after" in value)) {
        if (key === "password" && value.after === true) return "Senha alterada";
        return `${fieldLabel(key)}: ${formatMetadataValue(value.before)} -> ${formatMetadataValue(value.after)}`;
      }
      return `${fieldLabel(key)}: ${formatMetadataValue(value)}`;
    })
    .join(" | ");
}

function fieldLabel(value: string) {
  if (FIELD_LABELS[value]) return FIELD_LABELS[value];
  return humanizeKey(value);
}

function humanizeKey(value: string) {
  return value.replaceAll("_", " ");
}

function isPlainRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isCriticalAuditAction(action: string) {
  return (
    action.includes("failed") ||
    action.includes("error") ||
    action.startsWith("organization_") ||
    action.startsWith("agent_queue_action_") ||
    action.startsWith("agent_release_") ||
    action.startsWith("settings_") ||
    action.startsWith("monthly_report_email_settings_") ||
    action.startsWith("ldap_") ||
    action.startsWith("policy_") ||
    action.startsWith("quota_") ||
    action.startsWith("user_") ||
    action.startsWith("printer_")
  );
}

function auditActionLabel(action: string) {
  if (ACTION_LABELS[action]) return ACTION_LABELS[action];
  return humanizeKey(action);
}

function entityLabel(entity: string) {
  if (ENTITY_LABELS[entity]) return ENTITY_LABELS[entity];
  return humanizeKey(entity);
}

function auditActionClass(action: string, metadata?: Record<string, unknown>) {
  const status = typeof metadata?.status === "string" ? metadata.status : "";
  if (status === "failed" || action.includes("failed") || action.includes("error") || action.includes("deleted") || action.includes("blocked") || action.includes("cancelled")) {
    return "border-red-200 bg-red-50 text-red-700";
  }
  if (action.includes("updated") || action.includes("reordered") || action.includes("settings")) {
    return "border-amber-200 bg-amber-50 text-amber-700";
  }
  if (action.includes("exported") || action.includes("generated") || action.includes("sent")) {
    return "border-blue-200 bg-blue-50 text-blue-700";
  }
  if (status === "succeeded" || action.includes("created") || action.includes("authorized") || action.includes("released") || action.includes("confirmed")) {
    return "border-emerald-200 bg-emerald-50 text-emerald-700";
  }
  return "border-slate-200 bg-slate-100 text-slate-700";
}

function buildAuditFilename(dateFrom: string, dateTo: string) {
  const suffix = dateFrom || dateTo ? `-${dateFrom || "inicio"}-${dateTo || "hoje"}` : "";
  return `auditoria${suffix}.csv`;
}

function readError(err: { message?: string }) {
  let errorText = err.message || "";
  try {
    const parsed = JSON.parse(errorText);
    if (parsed.detail) errorText = parsed.detail;
  } catch {}
  return errorText || "Erro desconhecido";
}
