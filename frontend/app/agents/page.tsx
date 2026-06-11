"use client";

import { useEffect, useMemo, useState, type ComponentType } from "react";
import { Activity, AlertTriangle, CheckCircle2, Clock3, Cpu, FileText, MonitorCog, Network, Plus, RefreshCw, Search, Server, TerminalSquare, Trash2, Usb, X } from "lucide-react";

import { ProtectedPage } from "@/components/protected-page";
import { Button, Input, Surface } from "@/components/ui";
import { apiFetch, getCurrentRole } from "@/lib/api";

type AgentQueue = {
  id: number;
  printer_id: number | null;
  queue_name: string;
  computer_name: string | null;
  driver_name: string | null;
  port_name: string | null;
  connection_type: string | null;
  ip_address: string | null;
  serial_number: string | null;
  device_id: string | null;
  fingerprint: string | null;
  last_seen_at: string | null;
  is_present: boolean;
};

type AgentRecentJob = {
  id: number;
  username: string;
  printer_name: string;
  document_name: string | null;
  pages: number;
  is_color: boolean;
  status: string;
  policy_name: string | null;
  policy_action: string | null;
  submitted_at: string;
};

type AgentHealthAlert = {
  code: string;
  severity: "info" | "warning" | "error" | string;
  message: string;
};

type AgentLog = {
  id: number;
  level: string;
  message: string;
  source: string | null;
  occurred_at: string;
  received_at: string;
};

type AgentRow = {
  id: number;
  agent_uid: string;
  computer_name: string | null;
  os_user: string | null;
  version: string | null;
  ip_address: string | null;
  capture_mode: string | null;
  event_log_enabled: boolean | null;
  auto_update_enabled: boolean | null;
  local_admin: boolean | null;
  last_error: string | null;
  last_seen_at: string | null;
  last_seen_age_seconds: number | null;
  created_at: string;
  is_online: boolean;
  status: string;
  health_alerts: AgentHealthAlert[];
  aliases: AgentQueue[];
  recent_jobs: AgentRecentJob[];
  queue_actions: AgentQueueAction[];
  recent_logs: AgentLog[];
};

type AgentQueueAction = {
  id: number;
  action_type: QueueActionType;
  queue_name: string;
  driver_name: string | null;
  port_name: string | null;
  ip_address: string | null;
  status: "pending" | "running" | "succeeded" | "failed";
  result_message: string | null;
  requested_at: string;
  dispatched_at: string | null;
  completed_at: string | null;
};

type QueueActionType = "create_queue" | "remove_queue" | "restore_queue";

type PrinterOption = {
  id: number;
  name: string;
  ip_address?: string | null;
};

function formatDate(value: string | null) {
  if (!value) return "-";
  return new Intl.DateTimeFormat("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    year: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function formatAge(seconds: number | null) {
  if (seconds === null) return "-";
  if (seconds < 60) return "agora";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `ha ${minutes} min`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `ha ${hours} h`;
  const days = Math.floor(hours / 24);
  return `ha ${days} d`;
}

function captureLabel(mode: string | null) {
  if (mode === "event_log") return "Event Log";
  if (mode === "spool") return "Spooler";
  return "-";
}

function statusClass(agent: AgentRow) {
  if (!agent.is_online) return "border-red-200 bg-red-50 text-red-700";
  if (agent.health_alerts.some((alert) => alert.severity === "warning" || alert.severity === "error")) return "border-amber-200 bg-amber-50 text-amber-700";
  return "border-emerald-200 bg-emerald-50 text-emerald-700";
}

function statusLabel(agent: AgentRow) {
  if (!agent.is_online) return "Offline";
  if (agent.health_alerts.some((alert) => alert.severity === "error")) return "Erro";
  if (agent.health_alerts.some((alert) => alert.severity === "warning")) return "Atencao";
  return "Saudavel";
}

function alertClass(severity: string) {
  if (severity === "error") return "border-red-200 bg-red-50 text-red-700";
  if (severity === "warning") return "border-amber-200 bg-amber-50 text-amber-700";
  return "border-blue-200 bg-blue-50 text-blue-700";
}

function logLevelClass(level: string) {
  if (level === "error" || level === "critical") return "border-red-200 bg-red-50 text-red-700";
  if (level === "warning") return "border-amber-200 bg-amber-50 text-amber-700";
  return "border-slate-200 bg-slate-50 text-slate-700";
}

function queueActionLabel(actionType: QueueActionType) {
  if (actionType === "create_queue") return "Criar";
  if (actionType === "restore_queue") return "Restaurar";
  return "Remover";
}

function queueActionStatusLabel(action: AgentQueueAction) {
  if (isStaleQueueAction(action)) return "Travada";
  if (action.status === "pending") return "Pendente";
  if (action.status === "running") return "Executando";
  if (action.status === "succeeded") return "Concluida";
  return "Falhou";
}

function queueActionStatusClass(action: AgentQueueAction) {
  if (isStaleQueueAction(action)) return "border-amber-200 bg-amber-50 text-amber-700";
  if (action.status === "succeeded") return "border-emerald-200 bg-emerald-50 text-emerald-700";
  if (action.status === "failed") return "border-red-200 bg-red-50 text-red-700";
  return "border-blue-200 bg-blue-50 text-blue-700";
}

function policyActionLabel(action: string | null) {
  if (action === "allow") return "Excecao";
  if (action === "block") return "Bloqueio";
  if (action === "require_release") return "Liberacao";
  if (action === "force_mono") return "Cobrar P&B";
  return "Politica";
}

function isStaleQueueAction(action: AgentQueueAction) {
  if (action.status !== "pending" && action.status !== "running") return false;
  const reference = action.status === "running" ? action.dispatched_at : action.requested_at;
  if (!reference) return false;
  return Date.now() - new Date(reference).getTime() > 15 * 60 * 1000;
}

function canCancelQueueAction(action: AgentQueueAction) {
  return action.status === "pending" || action.status === "running";
}

function canRestoreQueue(queue: AgentQueue) {
  return Boolean(queue.printer_id && queue.driver_name && (queue.ip_address || queue.port_name));
}

function connectionLabel(type: string | null) {
  if (type === "usb") return "USB";
  if (type === "network") return "Rede";
  if (type === "shared") return "Compartilhada";
  if (type === "local") return "Local";
  return "Desconhecida";
}

function connectionClass(type: string | null) {
  if (type === "usb") return "border-amber-200 bg-amber-50 text-amber-700";
  if (type === "network") return "border-blue-200 bg-blue-50 text-blue-700";
  if (type === "shared") return "border-violet-200 bg-violet-50 text-violet-700";
  return "border-slate-200 bg-slate-100 text-slate-700";
}

function presentConnectionTypes(agent: AgentRow) {
  return Array.from(new Set(agent.aliases.filter((alias) => alias.is_present).map((alias) => alias.connection_type || null)));
}

function printerName(printers: PrinterOption[], printerId: number | null) {
  if (!printerId) return "Sem vinculo";
  return printers.find((printer) => printer.id === printerId)?.name || `#${printerId}`;
}

function hasAlert(agent: AgentRow, code: string) {
  return agent.health_alerts.some((alert) => alert.code === code);
}

function actionableAlertCount(agent: AgentRow) {
  return agent.health_alerts.filter((alert) => alert.severity === "warning" || alert.severity === "error").length;
}

function onlinePercent(total: number, online: number) {
  if (!total) return 0;
  return Math.round((online / total) * 100);
}

function plainTextKey(value: string | null | undefined) {
  return (value || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .trim()
    .toLowerCase()
    .replace(/\s+/g, " ");
}

function isGenericQueueName(value: string | null | undefined) {
  return ["documento de impressao", "print document", "user", "unknown"].includes(plainTextKey(value));
}

export default function AgentsPage() {
  const [agents, setAgents] = useState<AgentRow[]>([]);
  const [printers, setPrinters] = useState<PrinterOption[]>([]);
  const [isAdmin, setIsAdmin] = useState(false);
  const [selectedAgent, setSelectedAgent] = useState<AgentRow | null>(null);
  const [agentSearch, setAgentSearch] = useState("");
  const [agentStatusFilter, setAgentStatusFilter] = useState("all");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [queueForm, setQueueForm] = useState({ queue_name: "", driver_name: "", ip_address: "", port_name: "", printer_id: "" });
  const [bulkForm, setBulkForm] = useState({ queue_name: "", driver_name: "", ip_address: "", port_name: "", printer_id: "" });
  const [bulkActionType, setBulkActionType] = useState<QueueActionType>("create_queue");
  const [bulkScope, setBulkScope] = useState<"all" | "selected">("all");
  const [selectedBulkAgentIds, setSelectedBulkAgentIds] = useState<number[]>([]);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [bulkMessage, setBulkMessage] = useState<string | null>(null);

  async function load() {
    const token = localStorage.getItem("token");
    if (!token) return;
    setLoading(true);
    setError(null);
    try {
      const data = await apiFetch<AgentRow[]>("/agent/agents", token);
      setAgents(data);
      setSelectedBulkAgentIds((ids) => ids.filter((id) => data.some((agent) => agent.id === id)));
      apiFetch<PrinterOption[]>("/printers", token).then(setPrinters).catch(() => setPrinters([]));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao carregar agents");
      setAgents([]);
    } finally {
      setLoading(false);
    }
  }

  async function openAgent(agent: AgentRow) {
    const token = localStorage.getItem("token");
    if (!token) return;
    try {
      const data = await apiFetch<AgentRow>(`/agent/agents/${agent.id}`, token);
      setSelectedAgent(data);
    } catch {
      setSelectedAgent(agent);
    }
  }

  async function refreshSelectedAgent(agentId: number) {
    const token = localStorage.getItem("token");
    if (!token) return;
    const data = await apiFetch<AgentRow>(`/agent/agents/${agentId}`, token);
    setSelectedAgent(data);
  }

  async function createQueueAction(actionType: QueueActionType, queue?: AgentQueue) {
    if (!selectedAgent || !isAdmin) return;
    const token = localStorage.getItem("token");
    if (!token) return;
    setActionMessage(null);
    try {
      const payload =
        actionType === "create_queue" || actionType === "restore_queue"
          ? {
              action_type: actionType,
              queue_name: queue?.queue_name || queueForm.queue_name,
              printer_id: queue?.printer_id ?? (queueForm.printer_id ? Number(queueForm.printer_id) : null),
              driver_name: queue?.driver_name || queueForm.driver_name,
              ip_address: queue?.ip_address || queueForm.ip_address || null,
              port_name: queue?.port_name || queueForm.port_name || null,
            }
          : {
              action_type: actionType,
              queue_name: queue?.queue_name || queueForm.queue_name,
            };
      await apiFetch<AgentQueueAction>(`/agent/agents/${selectedAgent.id}/queue-actions`, token, {
        method: "POST",
        body: JSON.stringify(payload),
      });
      setActionMessage("Acao enviada para o agent.");
      if (actionType === "create_queue" || actionType === "restore_queue") {
        setQueueForm({ queue_name: "", driver_name: "", ip_address: "", port_name: "", printer_id: "" });
      }
      await refreshSelectedAgent(selectedAgent.id);
      await load();
    } catch (err) {
      setActionMessage(err instanceof Error ? err.message : "Falha ao enviar acao");
    }
  }

  async function cancelQueueAction(action: AgentQueueAction) {
    if (!selectedAgent || !isAdmin || !canCancelQueueAction(action)) return;
    const token = localStorage.getItem("token");
    if (!token) return;
    const confirmed = window.confirm(`Cancelar a acao "${queueActionLabel(action.action_type)}" para a fila "${action.queue_name}"?`);
    if (!confirmed) return;
    setActionMessage(null);
    try {
      await apiFetch<AgentQueueAction>(`/agent/queue-actions/${action.id}/cancel`, token, { method: "POST" });
      setActionMessage("Acao remota cancelada.");
      await refreshSelectedAgent(selectedAgent.id);
      await load();
    } catch (err) {
      setActionMessage(err instanceof Error ? err.message : "Falha ao cancelar acao");
    }
  }

  async function bindAlias(aliasId: number, printerId: string) {
    if (!isAdmin) return;
    const token = localStorage.getItem("token");
    if (!token) return;
    setActionMessage(null);
    try {
      await apiFetch(`/printers/aliases/${aliasId}`, token, {
        method: "PUT",
        body: JSON.stringify({ printer_id: printerId ? Number(printerId) : null }),
      });
      setActionMessage("Vinculo da fila atualizado.");
      if (selectedAgent) {
        await refreshSelectedAgent(selectedAgent.id);
      }
      await load();
    } catch (err) {
      setActionMessage(err instanceof Error ? err.message : "Falha ao vincular fila");
    }
  }

  function prepareManagedQueueFromAlias(queue: AgentQueue) {
    const printer = printers.find((item) => item.id === queue.printer_id);
    setQueueForm({
      queue_name: printer?.name || "",
      driver_name: queue.driver_name || "",
      ip_address: queue.ip_address || "",
      port_name: queue.port_name || "",
      printer_id: queue.printer_id?.toString() || "",
    });
    setActionMessage("Dados carregados. Ajuste o nome padrao da fila e clique em Criar ou Restaurar.");
  }

  async function createBulkQueueAction() {
    if (!isAdmin) return;
    const token = localStorage.getItem("token");
    if (!token) return;
    setBulkMessage(null);
    try {
      const actions = await apiFetch<AgentQueueAction[]>("/agent/queue-actions/bulk", token, {
        method: "POST",
        body: JSON.stringify({
          action_type: bulkActionType,
          queue_name: bulkForm.queue_name,
          printer_id: bulkForm.printer_id ? Number(bulkForm.printer_id) : null,
          driver_name: bulkForm.driver_name || null,
          ip_address: bulkForm.ip_address || null,
          port_name: bulkForm.port_name || null,
          apply_to_all: bulkScope === "all",
          agent_ids: bulkScope === "selected" ? selectedBulkAgentIds : [],
        }),
      });
      setBulkMessage(`${queueActionLabel(bulkActionType)} enviado para ${actions.length} agent(s).`);
      setBulkForm({ queue_name: "", driver_name: "", ip_address: "", port_name: "", printer_id: "" });
      setSelectedBulkAgentIds([]);
      setBulkScope("all");
      await load();
    } catch (err) {
      setBulkMessage(err instanceof Error ? err.message : "Falha ao aplicar fila em lote");
    }
  }

  useEffect(() => {
    const token = localStorage.getItem("token");
    setIsAdmin(token ? getCurrentRole(token) === "admin" : false);
    load();
    const interval = setInterval(load, 15000);
    return () => clearInterval(interval);
  }, []);

  const summary = useMemo(() => {
    const online = agents.filter((agent) => agent.is_online).length;
    const withError = agents.filter((agent) => agent.health_alerts.length > 0).length;
    const queues = agents.reduce((total, agent) => total + agent.aliases.filter((alias) => alias.is_present).length, 0);
    const unboundQueues = agents.reduce((total, agent) => total + agent.aliases.filter((alias) => alias.is_present && !alias.printer_id).length, 0);
    const usbQueues = agents.reduce((total, agent) => total + agent.aliases.filter((alias) => alias.is_present && alias.connection_type === "usb").length, 0);
    const genericQueues = agents.reduce((total, agent) => total + agent.aliases.filter((alias) => alias.is_present && isGenericQueueName(alias.queue_name)).length, 0);
    const queueActions = agents.reduce(
      (total, agent) => total + agent.queue_actions.filter((action) => action.status === "pending" || action.status === "running").length,
      0
    );
    return { total: agents.length, online, offline: agents.length - online, withError, queues, unboundQueues, usbQueues, genericQueues, queueActions };
  }, [agents]);
  const filteredAgents = useMemo(() => {
    const search = agentSearch.trim().toLowerCase();
    return agents.filter((agent) => {
      const matchesSearch =
        !search ||
        [
          agent.agent_uid,
          agent.computer_name,
          agent.os_user,
          agent.ip_address,
          agent.version,
          agent.capture_mode,
          ...agent.aliases.map((alias) => alias.queue_name),
          ...agent.aliases.map((alias) => alias.ip_address),
          ...agent.aliases.map((alias) => alias.serial_number),
          ...agent.aliases.map((alias) => alias.device_id),
          ...agent.aliases.map((alias) => alias.fingerprint),
        ]
          .filter(Boolean)
          .some((value) => String(value).toLowerCase().includes(search));

      const matchesStatus =
        agentStatusFilter === "all" ||
        (agentStatusFilter === "online" && agent.is_online) ||
        (agentStatusFilter === "offline" && !agent.is_online) ||
        (agentStatusFilter === "alerts" && agent.health_alerts.length > 0) ||
        (agentStatusFilter === "heartbeat-delayed" && hasAlert(agent, "heartbeat_delayed")) ||
        (agentStatusFilter === "outdated" && hasAlert(agent, "outdated_version")) ||
        (agentStatusFilter === "auto-update-off" && hasAlert(agent, "auto_update_disabled")) ||
        (agentStatusFilter === "local-admin-missing" && hasAlert(agent, "local_admin_missing")) ||
        (agentStatusFilter === "unbound" && hasAlert(agent, "unbound_queues")) ||
        (agentStatusFilter === "identity-conflict" && hasAlert(agent, "hardware_identity_conflict")) ||
        (agentStatusFilter === "weak-identity" && hasAlert(agent, "weak_queue_identity")) ||
        (agentStatusFilter === "generic" && hasAlert(agent, "generic_queue_names")) ||
        (agentStatusFilter === "stale" && hasAlert(agent, "stale_queues")) ||
        (agentStatusFilter === "usb" && agent.aliases.some((alias) => alias.is_present && alias.connection_type === "usb"));

      return matchesSearch && matchesStatus;
    });
  }, [agentSearch, agentStatusFilter, agents]);
  const canApplyBulkQueue =
    isAdmin &&
    Boolean(
      bulkForm.queue_name &&
        (bulkActionType === "remove_queue" || (bulkForm.printer_id && bulkForm.driver_name && (bulkForm.ip_address || bulkForm.port_name))),
    ) &&
    (bulkScope === "all" ? agents.length > 0 : selectedBulkAgentIds.length > 0);

  return (
    <ProtectedPage>
      <div className="mb-6 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Agents</h1>
          <p className="mt-1 text-sm text-muted-foreground">Operacao dos PCs que capturam impressoes, filas locais e acoes remotas.</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className="rounded-full border border-slate-200 bg-white px-3 py-1 text-xs font-semibold text-muted-foreground">
            Atualiza a cada 15s
          </span>
          <Button variant="outline" onClick={load} disabled={loading}>
            <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
            Atualizar
          </Button>
        </div>
      </div>

      <Surface className="mb-6 overflow-hidden">
        <div className="grid gap-0 lg:grid-cols-[1.2fr_0.8fr]">
          <div className="border-b p-5 lg:border-b-0 lg:border-r">
            <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
              <div>
                <div className="text-xs font-bold uppercase text-muted-foreground">Centro de operacao</div>
                <div className="mt-1 text-xl font-bold">Saude do parque de agents</div>
              </div>
              <span className={`inline-flex rounded-full border px-2.5 py-1 text-xs font-bold ${summary.offline || summary.withError ? "border-amber-200 bg-amber-50 text-amber-700" : "border-emerald-200 bg-emerald-50 text-emerald-700"}`}>
                {summary.offline || summary.withError ? "Requer atencao" : "Operacao normal"}
              </span>
            </div>
            <div className="mb-3 flex items-end gap-3">
              <div className="text-4xl font-bold">{onlinePercent(summary.total, summary.online)}%</div>
              <div className="pb-1 text-sm text-muted-foreground">
                {summary.online} de {summary.total} PC(s) online
              </div>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-slate-100">
              <div className="h-full rounded-full bg-emerald-500" style={{ width: `${onlinePercent(summary.total, summary.online)}%` }} />
            </div>
            <div className="mt-4 grid gap-2 sm:grid-cols-3">
              <SignalPill icon={CheckCircle2} label="Online" value={summary.online} tone="ok" />
              <SignalPill icon={Clock3} label="Offline" value={summary.offline} tone={summary.offline ? "danger" : "muted"} />
              <SignalPill icon={Network} label="Filas" value={summary.queues} tone="info" />
            </div>
          </div>
          <div className="grid gap-0 sm:grid-cols-2">
            <OpsTile
              icon={AlertTriangle}
              label="Alertas"
              value={summary.withError}
              detail="Agents com erro, aviso ou ajuste pendente"
              tone={summary.withError ? "warn" : "ok"}
              onClick={() => setAgentStatusFilter("alerts")}
            />
            <OpsTile
              icon={Network}
              label="Sem vinculo"
              value={summary.unboundQueues}
              detail="Filas ainda nao ligadas a uma impressora fisica"
              tone={summary.unboundQueues ? "warn" : "ok"}
              onClick={() => setAgentStatusFilter("unbound")}
            />
            <OpsTile
              icon={Usb}
              label="USB"
              value={summary.usbQueues}
              detail="Bilhetagem local sem SNMP de rede"
              tone={summary.usbQueues ? "info" : "muted"}
              onClick={() => setAgentStatusFilter("usb")}
            />
            <OpsTile
              icon={TerminalSquare}
              label="Acoes"
              value={summary.queueActions}
              detail="Criacao, restauracao ou remocao em andamento"
              tone={summary.queueActions ? "info" : "muted"}
              onClick={() => setAgentStatusFilter("all")}
            />
          </div>
        </div>
      </Surface>

      {error ? (
        <Surface className="mb-6 flex items-center gap-2 border-red-200 bg-red-50 p-4 text-sm text-red-800">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          {error}
        </Surface>
      ) : null}

      <Surface className="mb-6 p-4">
        <div className="mb-3 flex flex-wrap gap-2">
          {[
            ["all", "Todos"],
            ["online", "Online"],
            ["alerts", "Alertas"],
            ["unbound", "Sem vinculo"],
            ["generic", "Nome generico"],
            ["usb", "USB"],
          ].map(([value, label]) => (
            <button
              key={value}
              type="button"
              className={`rounded-md border px-3 py-1.5 text-xs font-bold transition-colors ${
                agentStatusFilter === value ? "border-primary bg-primary/10 text-primary" : "bg-white text-muted-foreground hover:border-primary/30"
              }`}
              onClick={() => setAgentStatusFilter(value)}
            >
              {label}
            </button>
          ))}
        </div>
        <div className="grid gap-3 md:grid-cols-[1fr_240px_auto] md:items-center">
          <label className="relative block">
            <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
            <Input
              className="pl-9"
              placeholder="Buscar por PC, usuario, IP, versao ou fila"
              value={agentSearch}
              onChange={(event) => setAgentSearch(event.target.value)}
            />
          </label>
          <select
            className="h-9 rounded-md border bg-white px-3 text-sm"
            value={agentStatusFilter}
            onChange={(event) => setAgentStatusFilter(event.target.value)}
          >
            <option value="all">Todos os status</option>
            <option value="online">Somente online</option>
            <option value="offline">Somente offline</option>
            <option value="alerts">Com alertas</option>
            <option value="heartbeat-delayed">Heartbeat atrasado</option>
            <option value="outdated">Versao desatualizada</option>
            <option value="auto-update-off">Auto-update desligado</option>
            <option value="local-admin-missing">Sem admin local</option>
            <option value="unbound">Filas sem vinculo</option>
            <option value="identity-conflict">Conflito fisico</option>
            <option value="weak-identity">Identidade fraca</option>
            <option value="generic">Filas genericas</option>
            <option value="stale">Filas ausentes</option>
            <option value="usb">Filas USB</option>
          </select>
          <div className="text-sm font-semibold text-muted-foreground">
            {filteredAgents.length} de {agents.length} agent(s)
          </div>
        </div>
      </Surface>

      {isAdmin ? (
        <Surface className="mb-6 p-4">
          <div className="mb-3 flex items-center gap-2">
            <TerminalSquare className="h-4 w-4 text-primary" />
            <div>
              <h2 className="text-sm font-bold">Aplicar fila gerenciada</h2>
              <p className="text-xs text-muted-foreground">Cria, restaura ou remove a mesma fila em PCs selecionados ou em todos os agents da empresa.</p>
            </div>
          </div>
          <div className="mb-3 flex flex-wrap items-center gap-2 text-sm">
            <span className="text-xs font-semibold uppercase text-muted-foreground">Acao</span>
            {(["create_queue", "restore_queue", "remove_queue"] as QueueActionType[]).map((actionType) => (
              <button
                key={actionType}
                type="button"
                className={`rounded-md border px-3 py-1.5 ${bulkActionType === actionType ? "border-primary bg-primary/10 text-primary" : "bg-white text-muted-foreground"}`}
                onClick={() => setBulkActionType(actionType)}
              >
                {queueActionLabel(actionType)}
              </button>
            ))}
          </div>
          <div className="mb-3 flex flex-wrap items-center gap-2 text-sm">
            <span className="text-xs font-semibold uppercase text-muted-foreground">Escopo</span>
            <button
              type="button"
              className={`rounded-md border px-3 py-1.5 ${bulkScope === "all" ? "border-primary bg-primary/10 text-primary" : "bg-white text-muted-foreground"}`}
              onClick={() => setBulkScope("all")}
            >
              Empresa inteira
            </button>
            <button
              type="button"
              className={`rounded-md border px-3 py-1.5 ${bulkScope === "selected" ? "border-primary bg-primary/10 text-primary" : "bg-white text-muted-foreground"}`}
              onClick={() => setBulkScope("selected")}
            >
              PCs selecionados
            </button>
            {bulkScope === "selected" ? <span className="text-xs text-muted-foreground">{selectedBulkAgentIds.length} selecionado(s)</span> : null}
          </div>
          {bulkScope === "selected" ? (
            <div className="mb-3 grid gap-2 md:grid-cols-2 xl:grid-cols-3">
              {filteredAgents.map((agent) => {
                const checked = selectedBulkAgentIds.includes(agent.id);
                return (
                  <label key={agent.id} className="flex cursor-pointer items-center gap-2 rounded-md border bg-white px-3 py-2 text-sm">
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={(event) => {
                        setSelectedBulkAgentIds((ids) =>
                          event.target.checked ? [...ids, agent.id] : ids.filter((id) => id !== agent.id),
                        );
                      }}
                    />
                    <span className="min-w-0">
                      <span className="block truncate font-semibold">{agent.computer_name || agent.agent_uid}</span>
                      <span className="block truncate text-xs text-muted-foreground">{agent.os_user || "-"} - {agent.status}</span>
                    </span>
                  </label>
                );
              })}
              {filteredAgents.length === 0 ? <div className="text-xs text-muted-foreground">Nenhum agent disponivel para selecao.</div> : null}
            </div>
          ) : null}
          <div className="grid gap-3 lg:grid-cols-[1fr_1fr_1fr_140px_140px_auto]">
            <Input
              placeholder="Nome padrao da fila"
              value={bulkForm.queue_name}
              onChange={(event) => setBulkForm({ ...bulkForm, queue_name: event.target.value })}
            />
            <select
              className="h-9 rounded-md border bg-white px-3 text-sm"
              value={bulkForm.printer_id}
              disabled={bulkActionType === "remove_queue"}
              onChange={(event) => {
                const printer = printers.find((item) => item.id.toString() === event.target.value);
                setBulkForm({
                  ...bulkForm,
                  printer_id: event.target.value,
                  ip_address: bulkForm.ip_address || printer?.ip_address || "",
                });
              }}
            >
              <option value="">Impressora fisica</option>
              {printers.map((printer) => (
                <option key={printer.id} value={printer.id}>
                  {printer.name}
                </option>
              ))}
            </select>
            <Input
              placeholder="Driver ja instalado"
              value={bulkForm.driver_name}
              disabled={bulkActionType === "remove_queue"}
              onChange={(event) => setBulkForm({ ...bulkForm, driver_name: event.target.value })}
            />
            <Input
              placeholder="IP"
              value={bulkForm.ip_address}
              disabled={bulkActionType === "remove_queue"}
              onChange={(event) => setBulkForm({ ...bulkForm, ip_address: event.target.value })}
            />
            <Input
              placeholder="Porta"
              value={bulkForm.port_name}
              disabled={bulkActionType === "remove_queue"}
              onChange={(event) => setBulkForm({ ...bulkForm, port_name: event.target.value })}
            />
            <Button
              type="button"
              onClick={createBulkQueueAction}
              disabled={!canApplyBulkQueue}
            >
              {bulkActionType === "remove_queue" ? <Trash2 className="h-4 w-4" /> : bulkActionType === "restore_queue" ? <RefreshCw className="h-4 w-4" /> : <Plus className="h-4 w-4" />}
              {queueActionLabel(bulkActionType)}
            </Button>
          </div>
          {bulkMessage ? <div className="mt-2 text-xs text-muted-foreground">{bulkMessage}</div> : null}
        </Surface>
      ) : null}

      <Surface className="overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-muted text-left">
            <tr>
              <th className="p-3">Computador</th>
              <th className="p-3">Captura</th>
              <th className="p-3">Filas locais</th>
              <th className="p-3">Ultimo contato</th>
              <th className="p-3">Status</th>
            </tr>
          </thead>
          <tbody>
            {filteredAgents.map((agent) => (
              <tr key={agent.id} className="border-t hover:bg-muted/40 cursor-pointer" onClick={() => openAgent(agent)}>
                <td className="p-3">
                  <div className="font-semibold">{agent.computer_name || agent.agent_uid}</div>
                  <div className="mt-0.5 text-xs text-muted-foreground">{agent.os_user || "-"} - {agent.ip_address || "sem IP"}</div>
                </td>
                <td className="p-3">
                  <div className="font-medium">{captureLabel(agent.capture_mode)}</div>
                  <div className={`mt-0.5 text-xs ${hasAlert(agent, "auto_update_disabled") ? "font-semibold text-amber-700" : "text-muted-foreground"}`}>
                    v{agent.version || "-"} - update {agent.auto_update_enabled ? "on" : "off"}
                  </div>
                  {hasAlert(agent, "auto_update_disabled") ? (
                    <div className="mt-1 text-xs font-semibold text-amber-700">Atualizar ou reinstalar agent</div>
                  ) : null}
                </td>
                <td className="p-3">
                  <div className="font-medium">
                    {agent.aliases.filter((alias) => alias.is_present).length}
                    {agent.aliases.some((alias) => !alias.is_present) ? <span className="text-xs text-muted-foreground"> / {agent.aliases.length}</span> : null}
                  </div>
                  <div className="mt-0.5 max-w-[320px] truncate text-xs text-muted-foreground">
                    {agent.aliases.filter((alias) => alias.is_present).map((alias) => alias.queue_name).join(", ") || "-"}
                  </div>
                  {presentConnectionTypes(agent).length > 0 ? (
                    <div className="mt-1 flex max-w-[320px] flex-wrap gap-1">
                      {presentConnectionTypes(agent).map((type) => (
                        <span key={type || "unknown"} className={`inline-flex rounded-full border px-1.5 py-0.5 text-[10px] font-semibold ${connectionClass(type)}`}>
                          {connectionLabel(type)}
                        </span>
                      ))}
                    </div>
                  ) : null}
                  {hasAlert(agent, "unbound_queues") || hasAlert(agent, "no_queues") || hasAlert(agent, "stale_queues") ? (
                    <div className="mt-1 text-xs font-semibold text-amber-700">Revisar vinculos de fila</div>
                  ) : null}
                </td>
                <td className="p-3">
                  <div className="font-medium" title={formatDate(agent.last_seen_at)}>
                    {formatAge(agent.last_seen_age_seconds)}
                  </div>
                  <div className="mt-0.5 text-xs text-muted-foreground">{formatDate(agent.last_seen_at)}</div>
                </td>
                <td className="p-3">
                  <span className={`inline-flex rounded-full border px-2.5 py-0.5 text-xs font-semibold ${statusClass(agent)}`}>
                    {statusLabel(agent)}
                  </span>
                  {actionableAlertCount(agent) > 0 ? (
                    <div className="mt-1 text-[10px] font-semibold text-amber-700">
                      {actionableAlertCount(agent)} ajuste(s) acionavel(is)
                    </div>
                  ) : null}
                  {agent.health_alerts.length > 0 ? (
                    <div className="mt-1 flex max-w-[320px] flex-wrap gap-1">
                      {agent.health_alerts.slice(0, 3).map((alert) => (
                        <span key={alert.code} className={`inline-flex max-w-[300px] truncate rounded-full border px-2 py-0.5 text-[10px] font-semibold ${alertClass(alert.severity)}`} title={alert.message}>
                          {alert.message}
                        </span>
                      ))}
                      {agent.health_alerts.length > 3 ? <span className="text-[10px] text-muted-foreground">+{agent.health_alerts.length - 3}</span> : null}
                    </div>
                  ) : null}
                </td>
              </tr>
            ))}
            {filteredAgents.length === 0 ? (
              <tr>
                <td className="p-6 text-center text-sm text-muted-foreground" colSpan={5}>
                  {agents.length === 0 ? "Nenhum agent enviou heartbeat ainda." : "Nenhum agent encontrado com os filtros atuais."}
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </Surface>

      {selectedAgent ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm" onClick={() => setSelectedAgent(null)}>
          <div className="max-h-[90vh] w-full max-w-4xl overflow-hidden rounded-lg bg-white shadow-2xl" onClick={(event) => event.stopPropagation()}>
            <div className="flex items-center justify-between border-b bg-slate-950 px-5 py-4 text-white">
              <div>
                <h2 className="text-lg font-bold">{selectedAgent.computer_name || selectedAgent.agent_uid}</h2>
                <p className="text-xs text-slate-300">{selectedAgent.agent_uid}</p>
              </div>
              <button className="text-white/80 transition-colors hover:text-white" onClick={() => setSelectedAgent(null)}>
                <X className="h-5 w-5" />
              </button>
            </div>
            <div className="grid max-h-[calc(90vh-72px)] gap-5 overflow-auto p-5">
              <div className="grid gap-3 md:grid-cols-4">
                <div className="rounded-md bg-muted/50 p-3">
                  <div className="flex items-center gap-2 text-xs font-semibold uppercase text-muted-foreground">
                    <Server className="h-4 w-4" />
                    IP
                  </div>
                  <div className="mt-1 font-mono text-sm">{selectedAgent.ip_address || "-"}</div>
                </div>
                <div className="rounded-md bg-muted/50 p-3">
                  <div className="flex items-center gap-2 text-xs font-semibold uppercase text-muted-foreground">
                    <Cpu className="h-4 w-4" />
                    Usuario
                  </div>
                  <div className="mt-1 text-sm font-semibold">{selectedAgent.os_user || "-"}</div>
                </div>
                <div className="rounded-md bg-muted/50 p-3">
                  <div className="flex items-center gap-2 text-xs font-semibold uppercase text-muted-foreground">
                    <Activity className="h-4 w-4" />
                    Captura
                  </div>
                  <div className="mt-1 text-sm font-semibold">{captureLabel(selectedAgent.capture_mode)}</div>
                </div>
                <div className="rounded-md bg-muted/50 p-3">
                  <div className="flex items-center gap-2 text-xs font-semibold uppercase text-muted-foreground">
                    <Clock3 className="h-4 w-4" />
                    Ultimo contato
                  </div>
                  <div className="mt-1 text-sm font-semibold" title={formatDate(selectedAgent.last_seen_at)}>
                    {formatAge(selectedAgent.last_seen_age_seconds)}
                  </div>
                  <div className="mt-0.5 text-xs text-muted-foreground">{formatDate(selectedAgent.last_seen_at)}</div>
                </div>
              </div>

              <div className="grid gap-3 md:grid-cols-3">
                <div className="rounded-md bg-muted/50 p-3">
                  <div className="flex items-center gap-2 text-xs font-semibold uppercase text-muted-foreground">
                    <MonitorCog className="h-4 w-4" />
                    Permissao local
                  </div>
                  <div className={`mt-1 text-sm font-semibold ${selectedAgent.local_admin === false ? "text-amber-700" : ""}`}>
                    {selectedAgent.local_admin === null ? "Nao informado" : selectedAgent.local_admin ? "Administrador" : "Sem administrador"}
                  </div>
                </div>
                <div className="rounded-md bg-muted/50 p-3">
                  <div className="flex items-center gap-2 text-xs font-semibold uppercase text-muted-foreground">
                    <Activity className="h-4 w-4" />
                    Event Log
                  </div>
                  <div className={`mt-1 text-sm font-semibold ${selectedAgent.event_log_enabled === false ? "text-amber-700" : ""}`}>
                    {selectedAgent.event_log_enabled === null ? "Nao informado" : selectedAgent.event_log_enabled ? "Ativo" : "Desativado"}
                  </div>
                </div>
                <div className="rounded-md bg-muted/50 p-3">
                  <div className="flex items-center gap-2 text-xs font-semibold uppercase text-muted-foreground">
                    <RefreshCw className="h-4 w-4" />
                    Auto-update
                  </div>
                  <div className={`mt-1 text-sm font-semibold ${selectedAgent.auto_update_enabled === false ? "text-amber-700" : ""}`}>
                    {selectedAgent.auto_update_enabled === null ? "Nao informado" : selectedAgent.auto_update_enabled ? "Ativo" : "Desativado"}
                  </div>
                </div>
              </div>

              {selectedAgent.last_error ? (
                <div className="rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
                  <div className="font-semibold">Ultimo erro</div>
                  <div className="mt-1">{selectedAgent.last_error}</div>
                </div>
              ) : null}

              {selectedAgent.health_alerts.length > 0 ? (
                <div className="rounded-md border bg-muted/20 p-4">
                  <h3 className="mb-3 text-sm font-bold">Alertas operacionais</h3>
                  <div className="grid gap-2">
                    {selectedAgent.health_alerts.map((alert) => (
                      <div key={alert.code} className={`rounded-md border px-3 py-2 text-sm ${alertClass(alert.severity)}`}>
                        {alert.message}
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}

              {isAdmin ? (
                <div className="rounded-md border bg-muted/20 p-4">
                  <div className="mb-3 flex items-center gap-2">
                    <TerminalSquare className="h-4 w-4 text-primary" />
                    <h3 className="text-sm font-bold">Administracao remota de filas</h3>
                  </div>
                  <div className="grid gap-3 md:grid-cols-[1fr_1fr_1fr_130px_130px_auto_auto]">
                    <Input
                      placeholder="Nome da fila"
                      value={queueForm.queue_name}
                      onChange={(event) => setQueueForm({ ...queueForm, queue_name: event.target.value })}
                    />
                    <select
                      className="h-9 rounded-md border bg-white px-3 text-sm"
                      value={queueForm.printer_id}
                      onChange={(event) => {
                        const printer = printers.find((item) => item.id.toString() === event.target.value);
                        setQueueForm({
                          ...queueForm,
                          printer_id: event.target.value,
                          ip_address: queueForm.ip_address || printer?.ip_address || "",
                        });
                      }}
                    >
                      <option value="">Impressora fisica</option>
                      {printers.map((printer) => (
                        <option key={printer.id} value={printer.id}>
                          {printer.name}
                        </option>
                      ))}
                    </select>
                    <Input
                      placeholder="Driver ja instalado"
                      value={queueForm.driver_name}
                      onChange={(event) => setQueueForm({ ...queueForm, driver_name: event.target.value })}
                    />
                    <Input
                      placeholder="IP"
                      value={queueForm.ip_address}
                      onChange={(event) => setQueueForm({ ...queueForm, ip_address: event.target.value })}
                    />
                    <Input
                      placeholder="Porta"
                      value={queueForm.port_name}
                      onChange={(event) => setQueueForm({ ...queueForm, port_name: event.target.value })}
                    />
                    <Button
                      type="button"
                      onClick={() => createQueueAction("create_queue")}
                      disabled={!queueForm.queue_name || !queueForm.printer_id || !queueForm.driver_name || (!queueForm.ip_address && !queueForm.port_name)}
                    >
                      <Plus className="h-4 w-4" />
                      Criar
                    </Button>
                    <Button
                      type="button"
                      variant="outline"
                      onClick={() => createQueueAction("restore_queue")}
                      disabled={!queueForm.queue_name || !queueForm.printer_id || !queueForm.driver_name || (!queueForm.ip_address && !queueForm.port_name)}
                    >
                      <RefreshCw className="h-4 w-4" />
                      Restaurar
                    </Button>
                  </div>
                  {actionMessage ? <div className="mt-2 text-xs text-muted-foreground">{actionMessage}</div> : null}
                </div>
              ) : null}

              <div>
                <h3 className="mb-2 text-sm font-bold">Filas locais</h3>
                <div className="overflow-hidden rounded-md border">
                  <table className="w-full text-sm">
                    <thead className="bg-muted text-left">
                      <tr>
                        <th className="p-3">Fila</th>
                        <th className="p-3">Conexao</th>
                        <th className="p-3">IP / Porta</th>
                        <th className="p-3">Vinculo</th>
                        {isAdmin ? <th className="p-3 text-right">Acao</th> : null}
                      </tr>
                    </thead>
                    <tbody>
                      {selectedAgent.aliases.map((queue) => (
                        <tr key={queue.id} className="border-t">
                          <td className="p-3">
                            <div className="font-semibold">{queue.queue_name}</div>
                            <div className="text-xs text-muted-foreground">{queue.driver_name || "-"}</div>
                            <span
                              className={`mt-1 inline-flex rounded-full border px-2 py-0.5 text-[10px] font-semibold ${
                                queue.is_present ? "border-emerald-200 bg-emerald-50 text-emerald-700" : "border-amber-200 bg-amber-50 text-amber-700"
                              }`}
                            >
                              {queue.is_present ? "Presente" : "Ausente"}
                            </span>
                            {isGenericQueueName(queue.queue_name) ? (
                              <span className="ml-1 mt-1 inline-flex rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 text-[10px] font-semibold text-amber-700">
                                Nome generico
                              </span>
                            ) : null}
                          </td>
                          <td className="p-3">
                            <span className={`inline-flex rounded-full border px-2 py-0.5 text-xs font-semibold ${connectionClass(queue.connection_type)}`}>
                              {connectionLabel(queue.connection_type)}
                            </span>
                            {queue.connection_type === "usb" ? (
                              <div className="mt-1 max-w-[180px] text-[10px] text-amber-700">
                                Bilhetagem ativa; SNMP indisponivel sem IP.
                              </div>
                            ) : null}
                          </td>
                          <td className="p-3">
                            <div className="font-mono text-xs">{queue.ip_address || "-"}</div>
                            <div className="text-xs text-muted-foreground">{queue.port_name || "-"}</div>
                            {queue.device_id ? (
                              <div className="mt-1 max-w-[220px] truncate font-mono text-[10px] text-muted-foreground" title={queue.device_id}>
                                {queue.device_id}
                              </div>
                            ) : null}
                          </td>
                          <td className="p-3">
                            {isAdmin ? (
                              <select
                                className={`h-8 max-w-[220px] rounded-md border bg-white px-2 text-xs font-semibold outline-none focus-visible:border-primary focus-visible:ring-2 focus-visible:ring-ring/20 ${
                                  queue.printer_id ? "border-emerald-200 text-emerald-700" : "border-amber-200 text-amber-700"
                                }`}
                                value={queue.printer_id?.toString() || ""}
                                onChange={(event) => bindAlias(queue.id, event.target.value)}
                                title="Vincular esta fila a uma impressora fisica"
                              >
                                <option value="">Sem vinculo</option>
                                {printers.map((printer) => (
                                  <option key={printer.id} value={printer.id}>
                                    {printer.name}
                                  </option>
                                ))}
                              </select>
                            ) : (
                              <span
                                className={`inline-flex max-w-[220px] rounded-full border px-2 py-0.5 text-xs font-semibold ${
                                  queue.printer_id ? "border-emerald-200 bg-emerald-50 text-emerald-700" : "border-amber-200 bg-amber-50 text-amber-700"
                                }`}
                                title={printerName(printers, queue.printer_id)}
                              >
                                <span className="truncate">{printerName(printers, queue.printer_id)}</span>
                              </span>
                            )}
                          </td>
                          {isAdmin ? (
                            <td className="p-3 text-right">
                              <div className="flex items-center justify-end gap-1">
                                <Button
                                  variant="ghost"
                                  className="h-8 w-8 p-0"
                                  title={canRestoreQueue(queue) ? "Restaurar fila neste PC" : "Restaurar exige impressora, driver e IP/porta"}
                                  disabled={!canRestoreQueue(queue)}
                                  onClick={() => createQueueAction("restore_queue", queue)}
                                >
                                  <RefreshCw className="h-4 w-4 text-primary" />
                                </Button>
                                {isGenericQueueName(queue.queue_name) ? (
                                  <Button
                                    variant="ghost"
                                    className="h-8 w-8 p-0"
                                    title="Carregar dados para criar uma fila com nome padronizado"
                                    disabled={!queue.printer_id || !queue.driver_name}
                                    onClick={() => prepareManagedQueueFromAlias(queue)}
                                  >
                                    <Plus className="h-4 w-4 text-emerald-600" />
                                  </Button>
                                ) : null}
                                <Button variant="ghost" className="h-8 w-8 p-0" title="Remover fila neste PC" onClick={() => createQueueAction("remove_queue", queue)}>
                                  <Trash2 className="h-4 w-4 text-red-600" />
                                </Button>
                              </div>
                            </td>
                          ) : null}
                        </tr>
                      ))}
                      {selectedAgent.aliases.length === 0 ? (
                        <tr>
                          <td className="p-4 text-center text-sm text-muted-foreground" colSpan={isAdmin ? 5 : 4}>
                            Nenhuma fila local detectada.
                          </td>
                        </tr>
                      ) : null}
                    </tbody>
                  </table>
                </div>
              </div>

              <div>
                <h3 className="mb-2 text-sm font-bold">Acoes remotas recentes</h3>
                <div className="overflow-hidden rounded-md border">
                  <table className="w-full text-sm">
                    <thead className="bg-muted text-left">
                      <tr>
                        <th className="p-3">Data</th>
                        <th className="p-3">Acao</th>
                        <th className="p-3">Fila</th>
                        <th className="p-3">Status</th>
                        <th className="p-3">Retorno</th>
                        {isAdmin ? <th className="p-3 text-right">Acao</th> : null}
                      </tr>
                    </thead>
                    <tbody>
                      {selectedAgent.queue_actions.map((action) => (
                        <tr key={action.id} className="border-t">
                          <td className="p-3">{formatDate(action.requested_at)}</td>
                          <td className="p-3">{queueActionLabel(action.action_type)}</td>
                          <td className="p-3 font-semibold">{action.queue_name}</td>
                          <td className="p-3">
                            <span className={`inline-flex rounded-full border px-2 py-0.5 text-xs font-semibold ${queueActionStatusClass(action)}`}>
                              {queueActionStatusLabel(action)}
                            </span>
                            {action.dispatched_at ? <div className="mt-1 text-[10px] text-muted-foreground">Despacho: {formatDate(action.dispatched_at)}</div> : null}
                          </td>
                          <td className="p-3 text-xs text-muted-foreground">{action.result_message || "-"}</td>
                          {isAdmin ? (
                            <td className="p-3 text-right">
                              {canCancelQueueAction(action) ? (
                                <Button
                                  variant="ghost"
                                  className="h-8 w-8 p-0"
                                  title="Cancelar acao remota"
                                  onClick={() => cancelQueueAction(action)}
                                >
                                  <X className="h-4 w-4 text-red-600" />
                                </Button>
                              ) : null}
                            </td>
                          ) : null}
                        </tr>
                      ))}
                      {selectedAgent.queue_actions.length === 0 ? (
                        <tr>
                          <td className="p-4 text-center text-sm text-muted-foreground" colSpan={isAdmin ? 6 : 5}>
                            Nenhuma acao remota enviada ainda.
                          </td>
                        </tr>
                      ) : null}
                    </tbody>
                  </table>
                </div>
              </div>

              <div>
                <h3 className="mb-2 text-sm font-bold">Logs recentes do agent</h3>
                <div className="overflow-hidden rounded-md border">
                  <table className="w-full text-sm">
                    <thead className="bg-muted text-left">
                      <tr>
                        <th className="p-3">Data</th>
                        <th className="p-3">Nivel</th>
                        <th className="p-3">Origem</th>
                        <th className="p-3">Mensagem</th>
                      </tr>
                    </thead>
                    <tbody>
                      {selectedAgent.recent_logs.map((log) => (
                        <tr key={log.id} className="border-t">
                          <td className="p-3">{formatDate(log.occurred_at)}</td>
                          <td className="p-3">
                            <span className={`inline-flex rounded-full border px-2 py-0.5 text-xs font-semibold ${logLevelClass(log.level)}`}>
                              {log.level}
                            </span>
                          </td>
                          <td className="p-3 text-xs text-muted-foreground">{log.source || "-"}</td>
                          <td className="p-3 text-xs">{log.message}</td>
                        </tr>
                      ))}
                      {selectedAgent.recent_logs.length === 0 ? (
                        <tr>
                          <td className="p-4 text-center text-sm text-muted-foreground" colSpan={4}>
                            Nenhum log recente recebido deste agent.
                          </td>
                        </tr>
                      ) : null}
                    </tbody>
                  </table>
                </div>
              </div>

              <div>
                <h3 className="mb-2 text-sm font-bold">Ultimos jobs</h3>
                <div className="overflow-hidden rounded-md border">
                  <table className="w-full text-sm">
                    <thead className="bg-muted text-left">
                      <tr>
                        <th className="p-3">Data</th>
                        <th className="p-3">Usuario</th>
                        <th className="p-3">Impressora</th>
                        <th className="p-3">Documento</th>
                        <th className="p-3">Politica</th>
                        <th className="p-3">Paginas</th>
                      </tr>
                    </thead>
                    <tbody>
                      {selectedAgent.recent_jobs.map((job) => (
                        <tr key={job.id} className="border-t">
                          <td className="p-3">{formatDate(job.submitted_at)}</td>
                          <td className="p-3 font-semibold">{job.username}</td>
                          <td className="p-3">{job.printer_name}</td>
                          <td className="p-3">
                            <div className="flex max-w-[240px] items-center gap-2 truncate">
                              <FileText className="h-4 w-4 shrink-0 text-muted-foreground" />
                              <span className="truncate">{job.document_name || "-"}</span>
                            </div>
                          </td>
                          <td className="p-3">
                            {job.policy_name ? (
                              <div>
                                <span className="inline-flex rounded-full border border-blue-200 bg-blue-50 px-2 py-0.5 text-xs font-semibold text-blue-700">
                                  {policyActionLabel(job.policy_action)}
                                </span>
                                <div className="mt-1 max-w-[180px] truncate text-xs font-medium" title={job.policy_name}>
                                  {job.policy_name}
                                </div>
                              </div>
                            ) : (
                              <span className="text-xs text-muted-foreground">-</span>
                            )}
                          </td>
                          <td className="p-3">{job.pages}</td>
                        </tr>
                      ))}
                      {selectedAgent.recent_jobs.length === 0 ? (
                        <tr>
                          <td className="p-4 text-center text-sm text-muted-foreground" colSpan={6}>
                            Nenhum job recente deste agent.
                          </td>
                        </tr>
                      ) : null}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </ProtectedPage>
  );
}

function SignalPill({
  icon: Icon,
  label,
  value,
  tone,
}: {
  icon: ComponentType<{ className?: string }>;
  label: string;
  value: number;
  tone: "ok" | "danger" | "info" | "muted";
}) {
  const toneClass =
    tone === "ok"
      ? "border-emerald-200 bg-emerald-50 text-emerald-700"
      : tone === "danger"
      ? "border-red-200 bg-red-50 text-red-700"
      : tone === "info"
      ? "border-blue-200 bg-blue-50 text-blue-700"
      : "border-slate-200 bg-slate-50 text-slate-700";

  return (
    <div className={`flex items-center justify-between rounded-md border px-3 py-2 ${toneClass}`}>
      <div>
        <div className="text-[11px] font-bold uppercase opacity-80">{label}</div>
        <div className="text-lg font-bold">{value}</div>
      </div>
      <Icon className="h-4 w-4" />
    </div>
  );
}

function OpsTile({
  icon: Icon,
  label,
  value,
  detail,
  tone,
  onClick,
}: {
  icon: ComponentType<{ className?: string }>;
  label: string;
  value: number;
  detail: string;
  tone: "ok" | "warn" | "info" | "muted";
  onClick: () => void;
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
    <button type="button" className="border-b p-4 text-left transition-colors hover:bg-muted/30 sm:border-r odd:sm:border-r" onClick={onClick}>
      <div className="mb-3 flex items-center justify-between gap-3">
        <div className="text-xs font-bold uppercase text-muted-foreground">{label}</div>
        <span className={`flex h-8 w-8 items-center justify-center rounded-md border ${toneClass}`}>
          <Icon className="h-4 w-4" />
        </span>
      </div>
      <div className="text-2xl font-bold">{value}</div>
      <div className="mt-1 text-xs leading-5 text-muted-foreground">{detail}</div>
    </button>
  );
}
