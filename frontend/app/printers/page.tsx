"use client";

import { FormEvent, useEffect, useState } from "react";
import { Edit, Plus, Server, Activity, Hash, Info } from "lucide-react";

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
              <tr key={printer.id} className="border-t animate-fade-in hover:bg-muted/30">
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
                    <div className="flex flex-col gap-1.5 w-32">
                      <div className="flex items-center justify-between text-xs">
                        <span className="font-medium text-muted-foreground">Toner:</span>
                        <span className={`font-bold ${
                          (printer.toner_level ?? 0) <= 10 ? "text-red-600" :
                          (printer.toner_level ?? 0) <= 30 ? "text-amber-500" : "text-green-600"
                        }`}>
                          {printer.toner_level !== null ? `${printer.toner_level}%` : "N/A"}
                        </span>
                      </div>
                      {printer.toner_level !== null && (
                        <div className="h-2 w-full rounded-full bg-gray-200 overflow-hidden border border-gray-300">
                          <div
                            className={`h-full transition-all duration-500 ${
                              printer.toner_level <= 10 ? "bg-red-500 animate-pulse" :
                              printer.toner_level <= 30 ? "bg-amber-400" : "bg-emerald-500"
                            }`}
                            style={{ width: `${printer.toner_level}%` }}
                          />
                        </div>
                      )}
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
                  <Button variant="ghost" onClick={() => startEdit(printer)} title="Editar" className="h-8 w-8 p-0">
                    <Edit className="h-4 w-4 text-muted-foreground hover:text-foreground" />
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Surface>
    </ProtectedPage>
  );
}
