"use client";

import { FormEvent, useEffect, useState } from "react";
import { Activity, AlertTriangle, Cpu, Droplets, Edit, FileText, GitMerge, Hash, Info, Server, Trash2, X } from "lucide-react";

import { ProtectedPage } from "@/components/protected-page";
import { Button, Input, Surface } from "@/components/ui";
import { apiFetch, getCurrentRole } from "@/lib/api";

type PrinterRow = {
  id: number;
  name: string;
  location: string | null;
  is_color: boolean;
  cost_mono: number;
  cost_color: number;
  is_active: boolean;
  ip_address: string | null;
  toner_level: number | null;
  toner_levels: Record<string, number> | null;
  paper_status: string | null;
  serial_number: string | null;
  page_counter: number | null;
  aliases?: {
    id: number;
    printer_id: number | null;
    queue_name: string;
    computer_name: string | null;
    driver_name: string | null;
    connection_type: string | null;
    ip_address: string | null;
    serial_number: string | null;
    device_id: string | null;
    fingerprint: string | null;
    port_name: string | null;
  }[];
};

type GeneralSettings = {
  default_printer_cost_mono: number;
  default_printer_cost_color: number;
};

type PrinterForm = {
  name: string;
  location: string;
  is_color: boolean;
  cost_mono: string;
  cost_color: string;
  is_active: boolean;
  ip_address: string;
};

const FALLBACK_PRINTER_COSTS = {
  mono: "0.05",
  color: "0.25",
};

function emptyPrinterForm(costs = FALLBACK_PRINTER_COSTS): PrinterForm {
  return {
    name: "",
    location: "",
    is_color: false,
    cost_mono: costs.mono,
    cost_color: costs.color,
    is_active: true,
    ip_address: "",
  };
}

function costText(value: number | null | undefined, fallback: string) {
  return value !== null && value !== undefined ? value.toFixed(2) : fallback;
}

export default function PrintersPage() {
  const [printers, setPrinters] = useState<PrinterRow[]>([]);
  const [isAdmin, setIsAdmin] = useState(false);
  const [defaultCosts, setDefaultCosts] = useState(FALLBACK_PRINTER_COSTS);
  const [form, setForm] = useState<PrinterForm>(() => emptyPrinterForm());
  const [error, setError] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [selectedPrinter, setSelectedPrinter] = useState<PrinterRow | null>(null);
  const [mergingPrinter, setMergingPrinter] = useState<PrinterRow | null>(null);
  const [mergeTargetId, setMergeTargetId] = useState("");

  async function load(): Promise<PrinterRow[]> {
    const token = localStorage.getItem("token");
    if (!token) return [];
    try {
      const rows = await apiFetch<PrinterRow[]>("/printers", token);
      setPrinters(rows);
      setSelectedPrinter((current) => rows.find((printer) => printer.id === current?.id) ?? current);
      return rows;
    } catch {
      setPrinters([]);
      return [];
    }
  }

  async function loadSettings() {
    const token = localStorage.getItem("token");
    if (!token) return;
    await apiFetch<GeneralSettings>("/settings", token)
      .then((data) => {
        const costs = {
          mono: String(data.default_printer_cost_mono ?? Number(FALLBACK_PRINTER_COSTS.mono)),
          color: String(data.default_printer_cost_color ?? Number(FALLBACK_PRINTER_COSTS.color)),
        };
        setDefaultCosts(costs);
        setForm((current) => ({
          ...current,
          cost_mono: current.cost_mono === FALLBACK_PRINTER_COSTS.mono ? costs.mono : current.cost_mono,
          cost_color: current.cost_color === FALLBACK_PRINTER_COSTS.color ? costs.color : current.cost_color,
        }));
      })
      .catch(() => setDefaultCosts(FALLBACK_PRINTER_COSTS));
  }

  useEffect(() => {
    const token = localStorage.getItem("token");
    setIsAdmin(token ? getCurrentRole(token) === "admin" : false);
    loadSettings();
    load();
    // Poll printer status every 10 seconds for SNMP updates
    const interval = setInterval(load, 10000);
    return () => clearInterval(interval);
  }, []);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!isAdmin) return;
    const token = localStorage.getItem("token");
    if (!token) return;
    setError(null);
    try {
      if (editingId) {
        await apiFetch<PrinterRow>(`/printers/${editingId}`, token, {
          method: "PUT",
          body: JSON.stringify({
            name: form.name,
            location: form.location || null,
            is_color: form.is_color,
            cost_mono: Number(form.cost_mono),
            cost_color: Number(form.cost_color),
            is_active: form.is_active,
            ip_address: form.ip_address || null,
          }),
        });
        setEditingId(null);
      } else {
        await apiFetch<PrinterRow>("/printers", token, {
          method: "POST",
          body: JSON.stringify({
            name: form.name,
            location: form.location || null,
            is_color: form.is_color,
            cost_mono: Number(form.cost_mono),
            cost_color: Number(form.cost_color),
            ip_address: form.ip_address || null,
          }),
        });
      }
      setForm(emptyPrinterForm(defaultCosts));
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao processar impressora");
    }
  }

  function startEdit(printer: PrinterRow) {
    if (!isAdmin) return;
    setEditingId(printer.id);
    setForm({
      name: printer.name,
      location: printer.location ?? "",
      is_color: printer.is_color,
      cost_mono: String(printer.cost_mono ?? Number(defaultCosts.mono)),
      cost_color: String(printer.cost_color ?? Number(defaultCosts.color)),
      is_active: printer.is_active,
      ip_address: printer.ip_address ?? "",
    });
  }

  async function deletePrinter(printer: PrinterRow) {
    if (!isAdmin) return;
    const confirmed = window.confirm(`Excluir a impressora "${printer.name}"? Impressoras com historico devem ser desativadas ou mescladas para preservar relatorios.`);
    if (!confirmed) return;
    const token = localStorage.getItem("token");
    if (!token) return;
    setError(null);
    try {
      await apiFetch<{ status: string; deleted_jobs: number }>(`/printers/${printer.id}`, token, { method: "DELETE" });
      if (editingId === printer.id) {
        setEditingId(null);
        setForm(emptyPrinterForm(defaultCosts));
      }
      if (selectedPrinter?.id === printer.id) {
        setSelectedPrinter(null);
      }
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao excluir impressora");
    }
  }

  async function mergePrinter() {
    if (!isAdmin) return;
    if (!mergingPrinter || !mergeTargetId) return;
    const target = printers.find((printer) => printer.id.toString() === mergeTargetId);
    if (!target) return;
    const confirmed = window.confirm(`Unir "${mergingPrinter.name}" em "${target.name}"? Os historicos serao movidos para a impressora de destino.`);
    if (!confirmed) return;
    const token = localStorage.getItem("token");
    if (!token) return;
    setError(null);
    try {
      await apiFetch<PrinterRow>(`/printers/${mergingPrinter.id}/merge/${target.id}`, token, { method: "POST" });
      setMergingPrinter(null);
      setMergeTargetId("");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao unir impressoras");
    }
  }

  async function bindAlias(aliasId: number, printerId: string) {
    if (!isAdmin) return;
    const token = localStorage.getItem("token");
    if (!token) return;
    setError(null);
    try {
      const updatedAlias = await apiFetch<{ printer_id: number | null }>(`/printers/aliases/${aliasId}`, token, {
        method: "PUT",
        body: JSON.stringify({ printer_id: printerId ? Number(printerId) : null }),
      });
      const rows = await load();
      if (updatedAlias.printer_id) {
        setSelectedPrinter(rows.find((printer) => printer.id === updatedAlias.printer_id) ?? null);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao vincular fila");
    }
  }

  function tonerEntries(printer: PrinterRow) {
    return Object.entries(printer.toner_levels ?? {});
  }

  function tonerLabel(key: string) {
    const labels: Record<string, string> = {
      black: "Preto",
      cyan: "Ciano",
      magenta: "Magenta",
      yellow: "Amarelo",
    };
    return labels[key] ?? key.replace(/_/g, " ");
  }

  function tonerBarColor(key: string, level: number) {
    if (level <= 10) return "bg-red-500 animate-pulse";
    if (level <= 30) return "bg-amber-400";
    if (key === "cyan") return "bg-cyan-500";
    if (key === "magenta") return "bg-fuchsia-500";
    if (key === "yellow") return "bg-yellow-400";
    if (key === "black") return "bg-neutral-800";
    return "bg-emerald-500";
  }

  function tonerTextColor(level: number | null) {
    if (level === null) return "text-muted-foreground";
    if (level <= 10) return "text-red-600";
    if (level <= 30) return "text-amber-500";
    return "text-green-600";
  }

  function connectionLabel(type?: string | null) {
    if (type === "usb") return "USB";
    if (type === "network") return "Rede";
    if (type === "shared") return "Compartilhada";
    if (type === "local") return "Local";
    return "Desconhecida";
  }

  function connectionClass(type?: string | null) {
    if (type === "usb") return "border-amber-200 bg-amber-50 text-amber-700";
    if (type === "network") return "border-blue-200 bg-blue-50 text-blue-700";
    if (type === "shared") return "border-violet-200 bg-violet-50 text-violet-700";
    return "border-slate-200 bg-slate-100 text-slate-700";
  }

  function connectionSummary(printer: PrinterRow) {
    const aliases = printer.aliases ?? [];
    if (printer.ip_address) return "Rede/SNMP";
    if (aliases.some((alias) => alias.connection_type === "usb")) return "USB sem SNMP";
    if (aliases.length > 0) return "Fila local";
    return "Sem monitoramento";
  }

  return (
    <ProtectedPage>
      <div className="mb-6">
        <h1 className="text-2xl font-bold tracking-tight">Impressoras</h1>
        <p className="text-sm text-muted-foreground">Adicione e gerencie filas de impressao e monitore o status do hardware via SNMP.</p>
      </div>

      {isAdmin ? (
        <Surface as="form" className="mb-6 flex flex-wrap gap-3 items-end p-4" onSubmit={submit}>
          <div className="grid gap-1.5 flex-1 min-w-[150px]">
            <label className="text-xs font-semibold text-muted-foreground">Fila de Impressao</label>
            <Input
              placeholder="Ex: Sala_TI"
              value={form.name}
              onChange={(event) => setForm({ ...form, name: event.target.value })}
              required
              disabled={editingId !== null}
            />
          </div>

          <div className="grid gap-1.5 flex-1 min-w-[150px]">
            <label className="text-xs font-semibold text-muted-foreground">Localizacao</label>
            <Input
              placeholder="Ex: Bloco B, Terreo"
              value={form.location}
              onChange={(event) => setForm({ ...form, location: event.target.value })}
            />
          </div>

          <div className="grid gap-1.5 w-40">
            <label className="text-xs font-semibold text-muted-foreground">Endereco IP (SNMP)</label>
            <Input
              placeholder="Ex: 192.168.1.50"
              value={form.ip_address}
              onChange={(event) => setForm({ ...form, ip_address: event.target.value })}
            />
          </div>

          <div className="grid gap-1.5 w-28">
            <label className="text-xs font-semibold text-muted-foreground">Custo P&B (R$)</label>
            <Input
              placeholder="0.05"
              type="number"
              step="0.01"
              value={form.cost_mono}
              onChange={(event) => setForm({ ...form, cost_mono: event.target.value })}
              required
            />
          </div>

          <div className="grid gap-1.5 w-28">
            <label className="text-xs font-semibold text-muted-foreground">Custo Cor (R$)</label>
            <Input
              placeholder="0.25"
              type="number"
              step="0.01"
              value={form.cost_color}
              onChange={(event) => setForm({ ...form, cost_color: event.target.value })}
              required
            />
          </div>

          <div className="flex gap-4 items-center mb-2 px-2 select-none">
            <label className="flex items-center gap-2 text-sm cursor-pointer font-medium">
              <input
                type="checkbox"
                className="h-4 w-4 rounded border-gray-300 text-primary focus:ring-primary"
                checked={form.is_color}
                onChange={(event) => setForm({ ...form, is_color: event.target.checked })}
              />
              Colorida
            </label>

            {editingId ? (
              <label className="flex items-center gap-2 text-sm cursor-pointer font-medium">
                <input
                  type="checkbox"
                  className="h-4 w-4 rounded border-gray-300 text-primary focus:ring-primary"
                  checked={form.is_active}
                  onChange={(event) => setForm({ ...form, is_active: event.target.checked })}
                />
                Ativa
              </label>
            ) : null}
          </div>

          <div className="flex gap-2 mb-0.5">
            <Button type="submit" className="px-5">
              {editingId ? "Salvar" : "Cadastrar"}
            </Button>
            {editingId ? (
              <Button
                type="button"
                variant="outline"
                onClick={() => {
                  setEditingId(null);
                  setForm(emptyPrinterForm(defaultCosts));
                }}
              >
                Cancelar
              </Button>
            ) : null}
          </div>
        </Surface>
      ) : null}

      {error ? (
        <Surface className="mb-6 p-4 text-sm bg-red-50 border-red-200 text-red-800 flex items-center gap-2">
          <Info className="h-5 w-5 text-red-600 shrink-0" />
          <span>{error}</span>
        </Surface>
      ) : null}

      {isAdmin && mergingPrinter ? (
        <Surface className="mb-6 flex flex-wrap items-end gap-3 p-4">
          <div className="min-w-[240px] flex-1">
            <div className="text-xs font-semibold text-muted-foreground">Unir impressora duplicada</div>
            <div className="mt-1 text-sm font-semibold">{mergingPrinter.name}</div>
          </div>
          <label className="grid min-w-[260px] flex-1 gap-1.5 text-xs font-semibold text-muted-foreground">
            Impressora de destino
            <select
              value={mergeTargetId}
              onChange={(event) => setMergeTargetId(event.target.value)}
              className="h-9 rounded-md border bg-white px-3 text-sm text-foreground outline-none focus-visible:border-primary focus-visible:ring-2 focus-visible:ring-ring/20"
            >
              <option value="">Selecione</option>
              {printers.filter((printer) => printer.id !== mergingPrinter.id).map((printer) => (
                <option key={printer.id} value={printer.id}>
                  {printer.name}
                </option>
              ))}
            </select>
          </label>
          <Button type="button" onClick={mergePrinter} disabled={!mergeTargetId}>
            <GitMerge className="h-4 w-4" />
            Unir
          </Button>
          <Button type="button" variant="outline" onClick={() => { setMergingPrinter(null); setMergeTargetId(""); }}>
            Cancelar
          </Button>
        </Surface>
      ) : null}

      <Surface className="overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-muted text-left">
            <tr>
              <th className="p-3">Fila / Hardware</th>
              <th className="p-3">Localizacao</th>
              <th className="p-3">IP / Monitoramento</th>
              <th className="p-3">Nivel Toner</th>
              <th className="p-3">Custos (P&B / Cor)</th>
              <th className="p-3">Status</th>
              <th className="p-3 text-right">Acoes</th>
            </tr>
          </thead>
          <tbody>
            {printers.map((printer) => (
              <tr
                key={printer.id}
                className="border-t animate-fade-in hover:bg-muted/30 cursor-pointer"
                onClick={() => setSelectedPrinter(printer)}
              >
                <td className="p-3">
                  <div className="font-semibold text-foreground">{printer.name}</div>
                  {printer.serial_number && (
                    <div className="text-[10px] text-muted-foreground font-mono flex items-center gap-0.5 mt-0.5">
                      <Hash className="h-3 w-3" />
                      <span>S/N: {printer.serial_number}</span>
                    </div>
                  )}
                  {(printer.aliases?.length ?? 0) > 0 && (
                    <div className="mt-1 flex flex-wrap gap-1">
                      <span className="text-[10px] text-muted-foreground">
                        {printer.aliases?.length} fila(s)
                      </span>
                      <span className={`inline-flex rounded-full border px-1.5 py-0.5 text-[10px] font-semibold ${connectionClass(printer.aliases?.[0]?.connection_type)}`}>
                        {connectionSummary(printer)}
                      </span>
                    </div>
                  )}
                </td>
                <td className="p-3">{printer.location ?? "-"}</td>
                <td className="p-3">
                  {printer.ip_address ? (
                    <div className="flex flex-col gap-0.5">
                      <div className="font-mono text-xs text-foreground flex items-center gap-1">
                        <Server className="h-3 w-3 text-muted-foreground" />
                        {printer.ip_address}
                      </div>
                      {printer.page_counter !== null && (
                        <div className="text-[10px] text-muted-foreground flex items-center gap-0.5">
                          <Activity className="h-3 w-3" />
                          <span>Hardware Counter: {printer.page_counter.toLocaleString()} pags</span>
                        </div>
                      )}
                    </div>
                  ) : (
                    <span className="text-muted-foreground text-xs italic">{connectionSummary(printer)}</span>
                  )}
                </td>
                <td className="p-3">
                  {printer.ip_address ? (
                    <div className="flex flex-col gap-1.5 w-40">
                      <div className="flex items-center justify-between text-xs">
                        <span className="font-medium text-muted-foreground">Toner:</span>
                        <span className={`font-bold ${tonerTextColor(printer.toner_level)}`}>
                          {printer.toner_level !== null ? `${printer.toner_level}%` : "N/A"}
                        </span>
                      </div>
                      {tonerEntries(printer).length > 0 ? (
                        <div className="grid gap-1">
                          {tonerEntries(printer).map(([key, level]) => (
                            <div key={key} className="grid grid-cols-[52px_1fr_32px] items-center gap-1 text-[10px]">
                              <span className="truncate text-muted-foreground">{tonerLabel(key)}</span>
                              <div className="h-1.5 rounded-full bg-gray-200 overflow-hidden border border-gray-300">
                                <div
                                  className={`h-full transition-all duration-500 ${tonerBarColor(key, level)}`}
                                  style={{ width: `${level}%` }}
                                />
                              </div>
                              <span className="text-right font-medium">{level}%</span>
                            </div>
                          ))}
                        </div>
                      ) : printer.toner_level !== null ? (
                        <div className="h-2 w-full rounded-full bg-gray-200 overflow-hidden border border-gray-300">
                          <div
                            className={`h-full transition-all duration-500 ${tonerBarColor("summary", printer.toner_level)}`}
                            style={{ width: `${printer.toner_level}%` }}
                          />
                        </div>
                      ) : null}
                    </div>
                  ) : (
                    <span className="text-muted-foreground text-xs">-</span>
                  )}
                </td>
                <td className="p-3">
                  <div className="font-medium text-foreground">
                    R$ {costText(printer.cost_mono, defaultCosts.mono)}{" "}
                    <span className="text-xs text-muted-foreground">/ R$ {costText(printer.cost_color, defaultCosts.color)}</span>
                  </div>
                  <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold mt-1 ${printer.is_color ? "bg-purple-50 text-purple-700 border border-purple-200" : "bg-gray-100 text-gray-700 border border-gray-200"}`}>
                    {printer.is_color ? "Suporta Colorido" : "Apenas P&B"}
                  </span>
                </td>
                <td className="p-3">
                  <div className="flex flex-col gap-1 items-start">
                    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ${printer.is_active ? "bg-green-50 text-green-700 border border-green-200" : "bg-red-50 text-red-700 border border-red-200"}`}>
                      {printer.is_active ? "Ativa" : "Inativa"}
                    </span>
                    {printer.ip_address && printer.paper_status && (
                      <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold border ${
                        printer.paper_status === "Pronta" ? "bg-green-50 text-green-700 border-green-200" :
                        printer.paper_status === "Toner Baixo" ? "bg-amber-50 text-amber-700 border-amber-200" :
                        "bg-red-50 text-red-700 border-red-200 animate-pulse"
                      }`}>
                        {printer.paper_status}
                      </span>
                    )}
                  </div>
                </td>
                <td className="p-3 text-right">
                  <div className="flex items-center justify-end gap-1">
                    {printer.ip_address && (
                      <Button variant="ghost" onClick={(e) => { e.stopPropagation(); setSelectedPrinter(printer); }} title="Detalhes SNMP" className="h-8 w-8 p-0">
                        <Info className="h-4 w-4 text-primary" />
                      </Button>
                    )}
                    {isAdmin ? (
                      <>
                        <Button variant="ghost" onClick={(e) => { e.stopPropagation(); startEdit(printer); }} title="Editar" className="h-8 w-8 p-0">
                          <Edit className="h-4 w-4 text-muted-foreground hover:text-foreground" />
                        </Button>
                        <Button variant="ghost" onClick={(e) => { e.stopPropagation(); setMergingPrinter(printer); setMergeTargetId(""); }} title="Unir duplicada" className="h-8 w-8 p-0">
                          <GitMerge className="h-4 w-4 text-muted-foreground hover:text-foreground" />
                        </Button>
                        <Button variant="ghost" onClick={(e) => { e.stopPropagation(); deletePrinter(printer); }} title="Excluir" className="h-8 w-8 p-0">
                          <Trash2 className="h-4 w-4 text-red-600 hover:text-red-700" />
                        </Button>
                      </>
                    ) : null}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Surface>

      {/* Printer Detail Modal */}
      {selectedPrinter && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm"
          onClick={() => setSelectedPrinter(null)}
        >
          <div
            className="bg-white rounded-xl shadow-2xl w-full max-w-lg mx-4 overflow-hidden animate-fade-in"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Header */}
            <div className="bg-gradient-to-r from-primary to-blue-700 px-6 py-4 flex items-center justify-between">
              <div>
                <h2 className="text-lg font-bold text-white">{selectedPrinter.name}</h2>
                {selectedPrinter.serial_number && (
                  <p className="text-xs text-white/70 font-mono mt-0.5">S/N: {selectedPrinter.serial_number}</p>
                )}
              </div>
              <button
                onClick={() => setSelectedPrinter(null)}
                className="text-white/80 hover:text-white transition-colors"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            {/* Body */}
            <div className="p-6 grid gap-5">
              {/* Status Row */}
              <div className="flex items-center gap-3">
                <div className={`h-3 w-3 rounded-full ${
                  selectedPrinter.paper_status === "Pronta" ? "bg-green-500" :
                  selectedPrinter.paper_status === "Toner Baixo" ? "bg-amber-500 animate-pulse" :
                  "bg-red-500 animate-pulse"
                }`} />
                <span className="text-sm font-semibold">
                  {selectedPrinter.paper_status || (selectedPrinter.ip_address ? "Sem dados" : "Sem monitoramento")}
                </span>
                {selectedPrinter.is_active ? (
                  <span className="ml-auto inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold bg-green-50 text-green-700 border border-green-200">Ativa</span>
                ) : (
                  <span className="ml-auto inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold bg-red-50 text-red-700 border border-red-200">Inativa</span>
                )}
              </div>

              {/* Info Grid */}
              <div className="grid grid-cols-2 gap-4">
                <div className="flex items-start gap-3 bg-muted/40 rounded-lg p-3">
                  <Server className="h-5 w-5 text-primary mt-0.5 shrink-0" />
                  <div>
                    <p className="text-[10px] text-muted-foreground font-semibold uppercase tracking-wide">Endereco IP</p>
                    <p className="text-sm font-mono font-medium">{selectedPrinter.ip_address || "-"}</p>
                  </div>
                </div>
                <div className="flex items-start gap-3 bg-muted/40 rounded-lg p-3">
                  <Cpu className="h-5 w-5 text-primary mt-0.5 shrink-0" />
                  <div>
                    <p className="text-[10px] text-muted-foreground font-semibold uppercase tracking-wide">Localizacao</p>
                    <p className="text-sm font-medium">{selectedPrinter.location || "-"}</p>
                  </div>
                </div>
                <div className="flex items-start gap-3 bg-muted/40 rounded-lg p-3">
                  <FileText className="h-5 w-5 text-primary mt-0.5 shrink-0" />
                  <div>
                    <p className="text-[10px] text-muted-foreground font-semibold uppercase tracking-wide">Contador de Paginas</p>
                    <p className="text-sm font-bold">{selectedPrinter.page_counter !== null ? selectedPrinter.page_counter.toLocaleString() : "-"}</p>
                  </div>
                </div>
                <div className="flex items-start gap-3 bg-muted/40 rounded-lg p-3">
                  <Hash className="h-5 w-5 text-primary mt-0.5 shrink-0" />
                  <div>
                    <p className="text-[10px] text-muted-foreground font-semibold uppercase tracking-wide">Numero de Serie</p>
                    <p className="text-sm font-mono font-medium">{selectedPrinter.serial_number || "-"}</p>
                  </div>
                </div>
              </div>

              {/* Toner Level */}
              {selectedPrinter.ip_address && (
                <div className="bg-muted/40 rounded-lg p-4">
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <Droplets className="h-5 w-5 text-primary" />
                      <span className="text-sm font-semibold">Nivel de Toner</span>
                    </div>
                    <span className={`text-lg font-bold ${tonerTextColor(selectedPrinter.toner_level)}`}>
                      {selectedPrinter.toner_level !== null ? `${selectedPrinter.toner_level}%` : "N/A"}
                    </span>
                  </div>
                  {tonerEntries(selectedPrinter).length > 0 ? (
                    <div className="grid gap-2">
                      {tonerEntries(selectedPrinter).map(([key, level]) => (
                        <div key={key} className="grid grid-cols-[72px_1fr_40px] items-center gap-2 text-xs">
                          <span className="truncate font-medium text-muted-foreground">{tonerLabel(key)}</span>
                          <div className="h-3 w-full rounded-full bg-gray-200 overflow-hidden border border-gray-300">
                            <div
                              className={`h-full rounded-full transition-all duration-700 ${tonerBarColor(key, level)}`}
                              style={{ width: `${level}%` }}
                            />
                          </div>
                          <span className="text-right font-semibold">{level}%</span>
                        </div>
                      ))}
                    </div>
                  ) : selectedPrinter.toner_level !== null ? (
                    <div className="h-3 w-full rounded-full bg-gray-200 overflow-hidden border border-gray-300">
                      <div
                        className={`h-full rounded-full transition-all duration-700 ${tonerBarColor("summary", selectedPrinter.toner_level)}`}
                        style={{ width: `${selectedPrinter.toner_level}%` }}
                      />
                    </div>
                  ) : null}
                  {(selectedPrinter.toner_level ?? 100) <= 10 && (
                    <div className="mt-2 flex items-center gap-1.5 text-xs text-red-600">
                      <AlertTriangle className="h-3.5 w-3.5" />
                      <span>Toner critico! Substituicao necessaria em breve.</span>
                    </div>
                  )}
                </div>
              )}

              {/* Costs */}
              <div className="flex items-center justify-between text-sm border-t pt-3">
                <span className="text-muted-foreground">Custo P&B / Cor:</span>
                <span className="font-semibold">
                  R$ {selectedPrinter.cost_mono.toFixed(2)} / R$ {selectedPrinter.cost_color.toFixed(2)}
                </span>
              </div>
              <div className="flex items-center justify-between text-sm">
                <span className="text-muted-foreground">Tipo:</span>
                <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ${
                  selectedPrinter.is_color ? "bg-purple-50 text-purple-700 border border-purple-200" : "bg-gray-100 text-gray-700 border border-gray-200"
                }`}>
                  {selectedPrinter.is_color ? "Suporta Colorido" : "Apenas P&B"}
                </span>
              </div>

              {(selectedPrinter.aliases?.length ?? 0) > 0 ? (
                <div className="border-t pt-3">
                  <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Filas detectadas</div>
                  <div className="grid gap-2">
                    {selectedPrinter.aliases?.map((alias) => (
                      <div key={alias.id} className="rounded-lg border bg-muted/20 p-3 text-xs">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <span className="font-semibold text-foreground">{alias.queue_name}</span>
                          <span className={`inline-flex rounded-full border px-2 py-0.5 font-semibold ${connectionClass(alias.connection_type)}`}>
                            {connectionLabel(alias.connection_type)}
                          </span>
                        </div>
                        <div className="mt-1 text-muted-foreground">
                          {alias.computer_name || "-"} {alias.port_name ? `| Porta: ${alias.port_name}` : ""}
                        </div>
                        {isAdmin ? (
                          <label className="mt-2 grid gap-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                            Vinculo fisico
                            <select
                              value={alias.printer_id?.toString() || ""}
                              onChange={(event) => bindAlias(alias.id, event.target.value)}
                              className={`h-8 rounded-md border bg-white px-2 text-xs normal-case tracking-normal outline-none focus-visible:border-primary focus-visible:ring-2 focus-visible:ring-ring/20 ${
                                alias.printer_id ? "border-emerald-200 text-emerald-700" : "border-amber-200 text-amber-700"
                              }`}
                              title="Mover esta fila para outra impressora fisica"
                            >
                              <option value="">Sem vinculo</option>
                              {printers.map((printer) => (
                                <option key={printer.id} value={printer.id}>
                                  {printer.name}
                                </option>
                              ))}
                            </select>
                          </label>
                        ) : null}
                        {alias.connection_type === "usb" ? (
                          <div className="mt-1 text-amber-700">USB: bilhetagem ativa, telemetria SNMP indisponivel sem IP de rede.</div>
                        ) : null}
                        {alias.device_id ? (
                          <div className="mt-1 truncate font-mono text-[10px] text-muted-foreground" title={alias.device_id}>
                            Device ID: {alias.device_id}
                          </div>
                        ) : null}
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}
            </div>

            {/* Footer */}
            <div className="bg-muted/30 px-6 py-3 flex justify-end gap-2 border-t">
              {isAdmin ? (
                <Button variant="outline" onClick={() => { setSelectedPrinter(null); startEdit(selectedPrinter); }}>
                  <Edit className="h-4 w-4 mr-1.5" />
                  Editar
                </Button>
              ) : null}
              <Button onClick={() => setSelectedPrinter(null)}>
                Fechar
              </Button>
            </div>
          </div>
        </div>
      )}
    </ProtectedPage>
  );
}
