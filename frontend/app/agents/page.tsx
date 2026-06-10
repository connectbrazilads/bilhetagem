"use client";

import { useEffect, useMemo, useState } from "react";
import { Activity, AlertTriangle, CheckCircle2, Clock3, Cpu, FileText, MonitorCog, Network, Plus, RefreshCw, Server, TerminalSquare, Trash2, X } from "lucide-react";

import { ProtectedPage } from "@/components/protected-page";
import { Button, Input, Surface } from "@/components/ui";
import { apiFetch } from "@/lib/api";

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
};

type AgentRecentJob = {
  id: number;
  username: string;
  printer_name: string;
  document_name: string | null;
  pages: number;
  is_color: boolean;
  status: string;
  submitted_at: string;
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
  last_error: string | null;
  last_seen_at: string | null;
  created_at: string;
  is_online: boolean;
  status: string;
  aliases: AgentQueue[];
  recent_jobs: AgentRecentJob[];
  queue_actions: AgentQueueAction[];
};

type AgentQueueAction = {
  id: number;
  action_type: "create_queue" | "remove_queue";
  queue_name: string;
  driver_name: string | null;
  port_name: string | null;
  ip_address: string | null;
  status: "pending" | "running" | "succeeded" | "failed";
  result_message: string | null;
  requested_at: string;
  completed_at: string | null;
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

function captureLabel(mode: string | null) {
  if (mode === "event_log") return "Event Log";
  if (mode === "spool") return "Spooler";
  return "-";
}

function statusClass(agent: AgentRow) {
  if (!agent.is_online) return "border-red-200 bg-red-50 text-red-700";
  if (agent.last_error) return "border-amber-200 bg-amber-50 text-amber-700";
  return "border-emerald-200 bg-emerald-50 text-emerald-700";
}

export default function AgentsPage() {
  const [agents, setAgents] = useState<AgentRow[]>([]);
  const [selectedAgent, setSelectedAgent] = useState<AgentRow | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [queueForm, setQueueForm] = useState({ queue_name: "", driver_name: "", ip_address: "", port_name: "" });
  const [actionMessage, setActionMessage] = useState<string | null>(null);

  async function load() {
    const token = localStorage.getItem("token");
    if (!token) return;
    setLoading(true);
    setError(null);
    try {
      const data = await apiFetch<AgentRow[]>("/agent/agents", token);
      setAgents(data);
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

  async function createQueueAction(actionType: "create_queue" | "remove_queue", queue?: AgentQueue) {
    if (!selectedAgent) return;
    const token = localStorage.getItem("token");
    if (!token) return;
    setActionMessage(null);
    try {
      const payload =
        actionType === "create_queue"
          ? {
              action_type: actionType,
              queue_name: queueForm.queue_name,
              driver_name: queueForm.driver_name,
              ip_address: queueForm.ip_address || null,
              port_name: queueForm.port_name || null,
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
      if (actionType === "create_queue") {
        setQueueForm({ queue_name: "", driver_name: "", ip_address: "", port_name: "" });
      }
      await refreshSelectedAgent(selectedAgent.id);
      await load();
    } catch (err) {
      setActionMessage(err instanceof Error ? err.message : "Falha ao enviar acao");
    }
  }

  useEffect(() => {
    load();
    const interval = setInterval(load, 15000);
    return () => clearInterval(interval);
  }, []);

  const summary = useMemo(() => {
    const online = agents.filter((agent) => agent.is_online).length;
    const withError = agents.filter((agent) => agent.last_error).length;
    const queues = agents.reduce((total, agent) => total + agent.aliases.length, 0);
    return { total: agents.length, online, offline: agents.length - online, withError, queues };
  }, [agents]);

  return (
    <ProtectedPage>
      <div className="mb-6 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Agents</h1>
          <p className="text-sm text-muted-foreground">Saude dos PCs que capturam impressoes e filas locais detectadas.</p>
        </div>
        <Button variant="outline" onClick={load} disabled={loading}>
          <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
          Atualizar
        </Button>
      </div>

      <div className="mb-6 grid gap-4 md:grid-cols-5">
        <Surface className="p-4">
          <div className="flex items-center justify-between text-sm text-muted-foreground">
            Total
            <MonitorCog className="h-4 w-4 text-primary" />
          </div>
          <div className="mt-2 text-2xl font-bold">{summary.total}</div>
        </Surface>
        <Surface className="p-4">
          <div className="flex items-center justify-between text-sm text-muted-foreground">
            Online
            <CheckCircle2 className="h-4 w-4 text-emerald-600" />
          </div>
          <div className="mt-2 text-2xl font-bold">{summary.online}</div>
        </Surface>
        <Surface className="p-4">
          <div className="flex items-center justify-between text-sm text-muted-foreground">
            Offline
            <Clock3 className="h-4 w-4 text-red-600" />
          </div>
          <div className="mt-2 text-2xl font-bold">{summary.offline}</div>
        </Surface>
        <Surface className="p-4">
          <div className="flex items-center justify-between text-sm text-muted-foreground">
            Alertas
            <AlertTriangle className="h-4 w-4 text-amber-600" />
          </div>
          <div className="mt-2 text-2xl font-bold">{summary.withError}</div>
        </Surface>
        <Surface className="p-4">
          <div className="flex items-center justify-between text-sm text-muted-foreground">
            Filas
            <Network className="h-4 w-4 text-primary" />
          </div>
          <div className="mt-2 text-2xl font-bold">{summary.queues}</div>
        </Surface>
      </div>

      {error ? (
        <Surface className="mb-6 flex items-center gap-2 border-red-200 bg-red-50 p-4 text-sm text-red-800">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          {error}
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
            {agents.map((agent) => (
              <tr key={agent.id} className="border-t hover:bg-muted/40 cursor-pointer" onClick={() => openAgent(agent)}>
                <td className="p-3">
                  <div className="font-semibold">{agent.computer_name || agent.agent_uid}</div>
                  <div className="mt-0.5 text-xs text-muted-foreground">{agent.os_user || "-"} - {agent.ip_address || "sem IP"}</div>
                </td>
                <td className="p-3">
                  <div className="font-medium">{captureLabel(agent.capture_mode)}</div>
                  <div className="mt-0.5 text-xs text-muted-foreground">v{agent.version || "-"} - update {agent.auto_update_enabled ? "on" : "off"}</div>
                </td>
                <td className="p-3">
                  <div className="font-medium">{agent.aliases.length}</div>
                  <div className="mt-0.5 max-w-[320px] truncate text-xs text-muted-foreground">
                    {agent.aliases.map((alias) => alias.queue_name).join(", ") || "-"}
                  </div>
                </td>
                <td className="p-3">{formatDate(agent.last_seen_at)}</td>
                <td className="p-3">
                  <span className={`inline-flex rounded-full border px-2.5 py-0.5 text-xs font-semibold ${statusClass(agent)}`}>
                    {agent.status}
                  </span>
                  {agent.last_error ? <div className="mt-1 max-w-[260px] truncate text-xs text-amber-700">{agent.last_error}</div> : null}
                </td>
              </tr>
            ))}
            {agents.length === 0 ? (
              <tr>
                <td className="p-6 text-center text-sm text-muted-foreground" colSpan={5}>
                  Nenhum agent enviou heartbeat ainda.
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
                  <div className="mt-1 text-sm font-semibold">{formatDate(selectedAgent.last_seen_at)}</div>
                </div>
              </div>

              {selectedAgent.last_error ? (
                <div className="rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
                  <div className="font-semibold">Ultimo erro</div>
                  <div className="mt-1">{selectedAgent.last_error}</div>
                </div>
              ) : null}

              <div className="rounded-md border bg-muted/20 p-4">
                <div className="mb-3 flex items-center gap-2">
                  <TerminalSquare className="h-4 w-4 text-primary" />
                  <h3 className="text-sm font-bold">Administracao remota de filas</h3>
                </div>
                <div className="grid gap-3 md:grid-cols-[1fr_1fr_140px_140px_auto]">
                  <Input
                    placeholder="Nome da fila"
                    value={queueForm.queue_name}
                    onChange={(event) => setQueueForm({ ...queueForm, queue_name: event.target.value })}
                  />
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
                    disabled={!queueForm.queue_name || !queueForm.driver_name || (!queueForm.ip_address && !queueForm.port_name)}
                  >
                    <Plus className="h-4 w-4" />
                    Criar
                  </Button>
                </div>
                {actionMessage ? <div className="mt-2 text-xs text-muted-foreground">{actionMessage}</div> : null}
              </div>

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
                        <th className="p-3 text-right">Acao</th>
                      </tr>
                    </thead>
                    <tbody>
                      {selectedAgent.aliases.map((queue) => (
                        <tr key={queue.id} className="border-t">
                          <td className="p-3">
                            <div className="font-semibold">{queue.queue_name}</div>
                            <div className="text-xs text-muted-foreground">{queue.driver_name || "-"}</div>
                          </td>
                          <td className="p-3">{queue.connection_type || "-"}</td>
                          <td className="p-3">
                            <div className="font-mono text-xs">{queue.ip_address || "-"}</div>
                            <div className="text-xs text-muted-foreground">{queue.port_name || "-"}</div>
                          </td>
                          <td className="p-3">
                            {queue.printer_id ? (
                              <span className="inline-flex rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-xs font-semibold text-emerald-700">Vinculada</span>
                            ) : (
                              <span className="inline-flex rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 text-xs font-semibold text-amber-700">Sem vinculo</span>
                            )}
                          </td>
                          <td className="p-3 text-right">
                            <Button variant="ghost" className="h-8 w-8 p-0" title="Remover fila neste PC" onClick={() => createQueueAction("remove_queue", queue)}>
                              <Trash2 className="h-4 w-4 text-red-600" />
                            </Button>
                          </td>
                        </tr>
                      ))}
                      {selectedAgent.aliases.length === 0 ? (
                        <tr>
                          <td className="p-4 text-center text-sm text-muted-foreground" colSpan={5}>
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
                      </tr>
                    </thead>
                    <tbody>
                      {selectedAgent.queue_actions.map((action) => (
                        <tr key={action.id} className="border-t">
                          <td className="p-3">{formatDate(action.requested_at)}</td>
                          <td className="p-3">{action.action_type === "create_queue" ? "Criar" : "Remover"}</td>
                          <td className="p-3 font-semibold">{action.queue_name}</td>
                          <td className="p-3">{action.status}</td>
                          <td className="p-3 text-xs text-muted-foreground">{action.result_message || "-"}</td>
                        </tr>
                      ))}
                      {selectedAgent.queue_actions.length === 0 ? (
                        <tr>
                          <td className="p-4 text-center text-sm text-muted-foreground" colSpan={5}>
                            Nenhuma acao remota enviada ainda.
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
                          <td className="p-3">{job.pages}</td>
                        </tr>
                      ))}
                      {selectedAgent.recent_jobs.length === 0 ? (
                        <tr>
                          <td className="p-4 text-center text-sm text-muted-foreground" colSpan={5}>
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
