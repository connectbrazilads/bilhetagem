"use client";

import { FormEvent, useEffect, useState } from "react";
import { Edit, Plus, Server, Activity, Hash, Info, X, Cpu, Droplets, FileText, Clock, AlertTriangle } from "lucide-react";

import { ProtectedPage } from "@/components/protected-page";
import { Button, Input, Surface } from "@/components/ui";
import { apiFetch } from "@/lib/api";

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
};

export default function PrintersPage() {
  const [printers, setPrinters] = useState<PrinterRow[]>([]);
  const [form, setForm] = useState({
    name: "",
    location: "",
    is_color: false,
    cost_mono: "0.05",
    cost_color: "0.25",
    is_active: true,
    ip_address: "",
  });
  const [error, setError] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [selectedPrinter, setSelectedPrinter] = useState<PrinterRow | null>(null);

  async function load() {
    const token = localStorage.getItem("token");
    if (!token) return;
    await apiFetch<PrinterRow[]>("/printers", token)
      .then(setPrinters)
      .catch(() => setPrinters([]));
  }

  useEffect(() => {
    load();
    // Poll printer status every 10 seconds for SNMP updates
    const interval = setInterval(load, 10000);
    return () => clearInterval(interval);
  }, []);

  async function submit(event: FormEvent) {
    event.preventDefault();
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
      setForm({
        name: "",
        location: "",
        is_color: false,
        cost_mono: "0.05",
        cost_color: "0.25",
        is_active: true,
        ip_address: "",
      });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao processar impressora");
    }
  }

  function startEdit(printer: PrinterRow) {
    setEditingId(printer.id);
    setForm({
      name: printer.name,
      location: printer.location ?? "",
      is_color: printer.is_color,
      cost_mono: String(printer.cost_mono ?? 0.05),
      cost_color: String(printer.cost_color ?? 0.25),
      is_active: printer.is_active,
      ip_address: printer.ip_address ?? "",
    });
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

  return (
    <ProtectedPage>
      <div className="mb-6">
        <h1 className="text-2xl font-bold tracking-tight">Impressoras</h1>
        <p className="text-sm text-muted-foreground">Adicione e gerencie filas de impressão e monitore o status do hardware via SNMP.</p>
      </div>

      <Surface as="form" className="mb-6 flex flex-wrap gap-3 items-end p-4" onSubmit={submit}>
        <div className="grid gap-1.5 flex-1 min-w-[150px]">
          <label className="text-xs font-semibold text-muted-foreground">Fila de Impressão</label>
          <Input
            placeholder="Ex: Sala_TI"
            value={form.name}
            onChange={(event) => setForm({ ...form, name: event.target.value })}
            required
            disabled={editingId !== null}
          />
        </div>
        
        <div className="grid gap-1.5 flex-1 min-w-[150px]">
          <label className="text-xs font-semibold text-muted-foreground">Localização</label>
          <Input
            placeholder="Ex: Bloco B, Térreo"
            value={form.location}
            onChange={(event) => setForm({ ...form, location: event.target.value })}
          />
        </div>

        <div className="grid gap-1.5 w-40">
          <label className="text-xs font-semibold text-muted-foreground">Endereço IP (SNMP)</label>
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
                setForm({
                  name: "",
                  location: "",
                  is_color: false,
                  cost_mono: "0.05",
                  cost_color: "0.25",
                  is_active: true,
                  ip_address: "",
                });
              }}
            >
              Cancelar
            </Button>
          ) : null}
        </div>
      </Surface>

      {error ? (
        <Surface className="mb-6 p-4 text-sm bg-red-50 border-red-200 text-red-800 flex items-center gap-2">
          <Info className="h-5 w-5 text-red-600 shrink-0" />
          <span>{error}</span>
        </Surface>
      ) : null}

      <Surface className="overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-muted text-left">
            <tr>
              <th className="p-3">Fila / Hardware</th>
              <th className="p-3">Localização</th>
              <th className="p-3">IP / Monitoramento</th>
              <th className="p-3">Nível Toner</th>
              <th className="p-3">Custos (P&B / Cor)</th>
              <th className="p-3">Status</th>
              <th className="p-3 text-right">Ações</th>
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
                          <span>Hardware Counter: {printer.page_counter.toLocaleString()} págs</span>
                        </div>
                      )}
                    </div>
                  ) : (
                    <span className="text-muted-foreground text-xs italic">Sem Monitoramento</span>
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
                    R$ {printer.cost_mono ? printer.cost_mono.toFixed(2) : "0.05"}{" "}
                    <span className="text-xs text-muted-foreground">/ R$ {printer.cost_color ? printer.cost_color.toFixed(2) : "0.25"}</span>
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
                    <Button variant="ghost" onClick={(e) => { e.stopPropagation(); startEdit(printer); }} title="Editar" className="h-8 w-8 p-0">
                      <Edit className="h-4 w-4 text-muted-foreground hover:text-foreground" />
                    </Button>
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
                    <p className="text-[10px] text-muted-foreground font-semibold uppercase tracking-wide">Endereço IP</p>
                    <p className="text-sm font-mono font-medium">{selectedPrinter.ip_address || "—"}</p>
                  </div>
                </div>
                <div className="flex items-start gap-3 bg-muted/40 rounded-lg p-3">
                  <Cpu className="h-5 w-5 text-primary mt-0.5 shrink-0" />
                  <div>
                    <p className="text-[10px] text-muted-foreground font-semibold uppercase tracking-wide">Localização</p>
                    <p className="text-sm font-medium">{selectedPrinter.location || "—"}</p>
                  </div>
                </div>
                <div className="flex items-start gap-3 bg-muted/40 rounded-lg p-3">
                  <FileText className="h-5 w-5 text-primary mt-0.5 shrink-0" />
                  <div>
                    <p className="text-[10px] text-muted-foreground font-semibold uppercase tracking-wide">Contador de Páginas</p>
                    <p className="text-sm font-bold">{selectedPrinter.page_counter !== null ? selectedPrinter.page_counter.toLocaleString() : "—"}</p>
                  </div>
                </div>
                <div className="flex items-start gap-3 bg-muted/40 rounded-lg p-3">
                  <Hash className="h-5 w-5 text-primary mt-0.5 shrink-0" />
                  <div>
                    <p className="text-[10px] text-muted-foreground font-semibold uppercase tracking-wide">Número de Série</p>
                    <p className="text-sm font-mono font-medium">{selectedPrinter.serial_number || "—"}</p>
                  </div>
                </div>
              </div>

              {/* Toner Level */}
              {selectedPrinter.ip_address && (
                <div className="bg-muted/40 rounded-lg p-4">
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <Droplets className="h-5 w-5 text-primary" />
                      <span className="text-sm font-semibold">Nível de Toner</span>
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
                      <span>Toner crítico! Substituição necessária em breve.</span>
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
            </div>

            {/* Footer */}
            <div className="bg-muted/30 px-6 py-3 flex justify-end gap-2 border-t">
              <Button variant="outline" onClick={() => { setSelectedPrinter(null); startEdit(selectedPrinter); }}>
                <Edit className="h-4 w-4 mr-1.5" />
                Editar
              </Button>
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
