"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Download, Filter, History, RefreshCcw } from "lucide-react";

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
      await downloadBlob(`/audit-logs/export?${params.toString()}`, "auditoria.csv", token);
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
    return {
      total: logs.length,
      actors: actors.size,
      entities: new Set(logs.map((log) => log.entity)).size,
    };
  }, [logs]);

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

      <div className="mb-4 grid gap-4 md:grid-cols-3">
        <Summary label="Eventos" value={summary.total} />
        <Summary label="Atores" value={summary.actors} />
        <Summary label="Entidades" value={summary.entities} />
      </div>

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
                {item}
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
                {item}
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
                      <span className="inline-flex rounded-full border bg-muted px-2 py-0.5 font-mono text-xs">{log.action}</span>
                    </td>
                    <td className="p-4">
                      <div className="font-medium">{log.entity}</div>
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

function Summary({ label, value }: { label: string; value: number }) {
  return (
    <Surface className="p-5">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-muted-foreground">{label}</span>
        <div className="flex h-9 w-9 items-center justify-center rounded-md bg-primary/10 text-primary">
          <History className="h-4 w-4" />
        </div>
      </div>
      <div className="mt-3 text-3xl font-semibold">{value.toLocaleString("pt-BR")}</div>
    </Surface>
  );
}

function formatMetadata(metadata: Record<string, unknown>) {
  const entries = Object.entries(metadata);
  if (!entries.length) return "-";
  return entries.map(([key, value]) => `${key}: ${formatMetadataValue(value)}`).join(" | ");
}

function formatMetadataValue(value: unknown) {
  if (value === null || value === undefined) return "-";
  if (typeof value === "object") {
    return JSON.stringify(value);
  }
  return String(value);
}

function readError(err: { message?: string }) {
  let errorText = err.message || "";
  try {
    const parsed = JSON.parse(errorText);
    if (parsed.detail) errorText = parsed.detail;
  } catch {}
  return errorText || "Erro desconhecido";
}
