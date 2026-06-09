"use client";

import { useEffect, useState } from "react";
import { FileText, Printer, Users, WalletCards, Check, X, ShieldAlert, Leaf, UploadCloud, Info } from "lucide-react";

import { ProtectedPage } from "@/components/protected-page";
import { Button, Surface } from "@/components/ui";
import { apiFetch, getCurrentUsername, API_URL, type DashboardMetrics } from "@/lib/api";

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

type PrinterInfo = {
  id: number;
  name: string;
  is_color: boolean;
  is_active: boolean;
};

function Stat({ label, value, isCurrency = false, icon: Icon }: { label: string; value: number; isCurrency?: boolean; icon: typeof FileText }) {
  return (
    <Surface className="p-4">
      <div className="flex items-center justify-between">
        <span className="text-sm text-muted-foreground">{label}</span>
        <Icon className="h-4 w-4 text-primary" />
      </div>
      <div className="mt-2 text-2xl font-semibold">
        {isCurrency ? `R$ ${value.toFixed(2)}` : value.toLocaleString("pt-BR")}
      </div>
    </Surface>
  );
}

export default function DashboardPage() {
  const [data, setData] = useState<DashboardMetrics | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [jobs, setJobs] = useState<JobRow[]>([]);
  const [username, setUsername] = useState<string | null>(null);
  const [safeReleaseEnabled, setSafeReleaseEnabled] = useState(false);

  // Web Print states
  const [printers, setPrinters] = useState<PrinterInfo[]>([]);
  const [selectedPrinterId, setSelectedPrinterId] = useState<string>("");
  const [isColorPrint, setIsColorPrint] = useState(false);
  const [fileToPrint, setFileToPrint] = useState<File | null>(null);
  const [webPrintStatus, setWebPrintStatus] = useState<{ text: string; type: "success" | "error" } | null>(null);
  const [webPrintLoading, setWebPrintLoading] = useState(false);

  async function loadMetrics() {
    const token = localStorage.getItem("token");
    if (!token) return;
    apiFetch<DashboardMetrics>("/reports", token).then(setData).catch((err) => setError(err.message));
  }

  async function loadJobs() {
    const token = localStorage.getItem("token");
    if (!token) return;
    try {
      const data = await apiFetch<JobRow[]>("/jobs", token);
      setJobs(data);
      setUsername(getCurrentUsername(token));
    } catch {
      setJobs([]);
    }
  }

  async function loadPrinters() {
    const token = localStorage.getItem("token");
    if (!token) return;
    try {
      const data = await apiFetch<PrinterInfo[]>("/printers", token);
      const activePrinters = data.filter(p => p.is_active);
      setPrinters(activePrinters);
      if (activePrinters.length > 0) {
        setSelectedPrinterId(activePrinters[0].id.toString());
      }
    } catch {
      setPrinters([]);
    }
  }

  async function loadSettings() {
    const token = localStorage.getItem("token");
    if (!token) return;
    try {
      const data = await apiFetch<{ safe_release_enabled: boolean }>("/settings", token);
      setSafeReleaseEnabled(data.safe_release_enabled);
    } catch {
      setSafeReleaseEnabled(false);
    }
  }

  useEffect(() => {
    loadMetrics();
    loadJobs();
    loadPrinters();
    loadSettings();
    
    // Poll for jobs periodically to update queue
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

  async function handleWebPrintSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!selectedPrinterId || !fileToPrint) {
      setWebPrintStatus({ text: "Selecione uma impressora e escolha um arquivo PDF.", type: "error" });
      return;
    }

    setWebPrintLoading(true);
    setWebPrintStatus(null);
    const token = localStorage.getItem("token") || "";

    const formData = new FormData();
    formData.append("file", fileToPrint);
    formData.append("printer_id", selectedPrinterId);
    formData.append("is_color", isColorPrint ? "true" : "false");

    try {
      const response = await fetch(`${API_URL}/jobs/web-print`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
        },
        body: formData,
      });

      if (!response.ok) {
        const detail = await response.text();
        let errorMsg = `Erro ${response.status}`;
        try {
          const parsed = JSON.parse(detail);
          if (parsed.detail) errorMsg = parsed.detail;
        } catch {}
        throw new Error(errorMsg);
      }

      const decision = await response.json();
      if (decision.authorized || decision.status === "pending_release") {
        setWebPrintStatus({
          text: decision.status === "pending_release"
            ? "Documento enviado com sucesso! Aguardando liberação na fila."
            : "Documento enviado e enviado diretamente para a impressora!",
          type: "success",
        });
        setFileToPrint(null);
        const fileInput = document.getElementById("web-print-file-input") as HTMLInputElement;
        if (fileInput) fileInput.value = "";

        await loadJobs();
        await loadMetrics();
      } else {
        setWebPrintStatus({
          text: `Impressão bloqueada: ${decision.reason || "Saldo ou cota insuficiente"}`,
          type: "error",
        });
      }
    } catch (err: any) {
      setWebPrintStatus({ text: `Falha no Web Print: ${err.message}`, type: "error" });
    } finally {
      setWebPrintLoading(false);
    }
  }

  // Filter pending release jobs for the current user
  const pendingJobs = jobs.filter(
    (job) => safeReleaseEnabled && job.status === "pending_release" && (username === "admin" || job.username === username)
  );

  const selectedPrinter = printers.find(p => p.id.toString() === selectedPrinterId);

  return (
    <ProtectedPage>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Dashboard</h1>
          <p className="text-sm text-muted-foreground">Consumo operacional e liberação segura de impressões em tempo real.</p>
        </div>
      </div>
      
      {error ? (
        <Surface className="mb-6 p-4 text-sm bg-red-50 border-red-200 text-red-800 flex items-center gap-2">
          <Info className="h-5 w-5 text-red-600 shrink-0" />
          <span>{error}</span>
        </Surface>
      ) : null}

      {/* Safe Release Queue Widget */}
      {pendingJobs.length > 0 ? (
        <Surface className="mb-6 border-primary/20 bg-primary/5 p-5">
          <div className="flex items-center gap-2 mb-4">
            <ShieldAlert className="h-5 w-5 text-primary" />
            <h2 className="text-lg font-semibold text-primary">Fila de Liberação Segura (Follow-Me)</h2>
            <span className="text-xs font-semibold text-primary bg-primary/15 px-2.5 py-0.5 rounded-full">
              {pendingJobs.length} pendente(s)
            </span>
          </div>
          <div className="space-y-3">
            {pendingJobs.map((job) => (
              <div key={job.id} className="flex flex-wrap items-center justify-between gap-3 border-b border-primary/10 pb-3 last:border-0 last:pb-0">
                <div>
                  <div className="text-sm font-semibold text-foreground">{job.document_name ?? "Trabalho de Impressão"}</div>
                  <div className="text-xs text-muted-foreground mt-0.5">
                    Impressora: <span className="font-semibold text-foreground">{job.printer_name}</span> | 
                    Usuário: <span className="font-semibold text-foreground">{job.username}</span> | 
                    Páginas: <span className="font-semibold text-foreground">{job.pages}</span> | 
                    Tipo: <span className={`font-semibold ${job.is_color ? "text-purple-600" : "text-foreground"}`}>{job.is_color ? "Colorido" : "Preto & Branco"}</span>
                  </div>
                </div>
                <div className="flex gap-2">
                  <Button className="h-8 text-xs px-3 bg-green-600 hover:bg-green-700 text-white" onClick={() => handleRelease(job.id)}>
                    <Check className="h-3.5 w-3.5 mr-1" />
                    Liberar
                  </Button>
                  <Button variant="outline" className="h-8 text-xs px-3 border-red-200 text-red-600 hover:bg-red-50 hover:text-red-700" onClick={() => handleCancel(job.id)}>
                    <X className="h-3.5 w-3.5 mr-1" />
                    Cancelar
                  </Button>
                </div>
              </div>
            ))}
          </div>
        </Surface>
      ) : null}

      <div className="grid gap-4 md:grid-cols-4">
        <Stat label="Impressões Hoje" value={data?.prints_today ?? 0} icon={FileText} />
        <Stat label="Páginas Hoje" value={data?.pages_today ?? 0} icon={Printer} />
        <Stat label="Impressões no Mês" value={data?.prints_month ?? 0} icon={Users} />
        <Stat label="Páginas no Mês" value={data?.pages_month ?? 0} icon={WalletCards} />
      </div>

      {/* Eco Dashboard Metrics */}
      {data?.eco_metrics ? (
        <div className="mt-4 grid gap-4 md:grid-cols-4 animate-fade-in">
          <Surface className="p-4 bg-emerald-50/50 border-emerald-100 flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between">
                <span className="text-sm text-emerald-800 font-semibold">Páginas Salvas</span>
                <Leaf className="h-4 w-4 text-emerald-600 animate-pulse" />
              </div>
              <div className="mt-2 text-2xl font-bold text-emerald-950">
                {data.eco_metrics.pages_saved.toLocaleString("pt-BR")}
              </div>
            </div>
            <div className="text-xs text-emerald-700/80 mt-1">Bloqueios e cancelamentos</div>
          </Surface>
          <Surface className="p-4 bg-emerald-50/50 border-emerald-100 flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between">
                <span className="text-sm text-emerald-800 font-semibold">Árvores Salvas</span>
                <Leaf className="h-4 w-4 text-emerald-600" />
              </div>
              <div className="mt-2 text-2xl font-bold text-emerald-950">
                {data.eco_metrics.trees_saved.toFixed(4)}
              </div>
            </div>
            <div className="text-xs text-emerald-700/80 mt-1">Impacto florestal reduzido</div>
          </Surface>
          <Surface className="p-4 bg-emerald-50/50 border-emerald-100 flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between">
                <span className="text-sm text-emerald-800 font-semibold">Água Preservada</span>
                <Leaf className="h-4 w-4 text-emerald-600" />
              </div>
              <div className="mt-2 text-2xl font-bold text-emerald-950">
                {data.eco_metrics.water_saved_l.toLocaleString("pt-BR")} L
              </div>
            </div>
            <div className="text-xs text-emerald-700/80 mt-1">Consumo industrial evitado</div>
          </Surface>
          <Surface className="p-4 bg-emerald-50/50 border-emerald-100 flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between">
                <span className="text-sm text-emerald-800 font-semibold">CO₂ Evitado</span>
                <Leaf className="h-4 w-4 text-emerald-600" />
              </div>
              <div className="mt-2 text-2xl font-bold text-emerald-950">
                {data.eco_metrics.co2_saved_g >= 1000 
                  ? `${(data.eco_metrics.co2_saved_g / 1000).toFixed(2)} kg` 
                  : `${data.eco_metrics.co2_saved_g.toFixed(0)} g`}
              </div>
            </div>
            <div className="text-xs text-emerald-700/80 mt-1">Gases estufa prevenidos</div>
          </Surface>
        </div>
      ) : null}

      {/* Web Print Card */}
      <Surface className="mt-4 p-5">
        <h2 className="text-lg font-bold flex items-center gap-2 mb-1">
          <UploadCloud className="h-5 w-5 text-primary" />
          <span>Web Print (Impressão Direta de PDF)</span>
        </h2>
        <p className="text-sm text-muted-foreground mb-4">
          Envie documentos em formato PDF diretamente do seu navegador sem precisar instalar drivers de impressora.
        </p>
        
        <form onSubmit={handleWebPrintSubmit} className="grid gap-4 md:grid-cols-3 items-end">
          <div className="grid gap-1.5">
            <label className="text-xs font-semibold text-muted-foreground">1. Escolha a Impressora</label>
            <select
              value={selectedPrinterId}
              onChange={(e) => {
                setSelectedPrinterId(e.target.value);
                const printer = printers.find(p => p.id.toString() === e.target.value);
                if (printer && !printer.is_color) {
                  setIsColorPrint(false);
                }
              }}
              className="h-9 w-full rounded-md border bg-background px-3 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring cursor-pointer"
              required
            >
              <option value="" disabled>Selecione uma impressora</option>
              {printers.map((printer) => (
                <option key={printer.id} value={printer.id}>
                  {printer.name} {printer.is_color ? "(Suporta Cores)" : "(Apenas P&B)"}
                </option>
              ))}
            </select>
          </div>

          <div className="grid gap-1.5">
            <label className="text-xs font-semibold text-muted-foreground">2. Selecione o Documento PDF</label>
            <input
              id="web-print-file-input"
              type="file"
              accept=".pdf"
              onChange={(e) => setFileToPrint(e.target.files?.[0] || null)}
              className="h-9 w-full rounded-md border bg-background px-3 py-1 text-sm outline-none file:mr-4 file:py-0.5 file:px-2.5 file:rounded-md file:border-0 file:text-xs file:font-semibold file:bg-primary file:text-primary-foreground hover:file:bg-primary/95 cursor-pointer"
              required
            />
          </div>

          <div className="flex gap-4 items-center justify-between">
            <label className={`flex items-center gap-2 text-sm cursor-pointer select-none font-medium mb-1.5 ${
              selectedPrinter && !selectedPrinter.is_color ? "opacity-50 cursor-not-allowed" : ""
            }`}>
              <input
                type="checkbox"
                className="h-4 w-4 rounded border-gray-300 text-primary focus:ring-primary disabled:cursor-not-allowed"
                checked={isColorPrint}
                disabled={!selectedPrinter?.is_color}
                onChange={(e) => setIsColorPrint(e.target.checked)}
              />
              Impressão Colorida
            </label>

            <Button type="submit" disabled={webPrintLoading || !fileToPrint} className="px-5">
              {webPrintLoading ? "Enviando..." : "Enviar para Impressão"}
            </Button>
          </div>
        </form>

        {webPrintStatus && (
          <div className={`mt-4 text-sm font-semibold flex items-center gap-2 p-3 rounded-md border ${
            webPrintStatus.type === "success" 
              ? "bg-green-50 border-green-200 text-green-800" 
              : "bg-red-50 border-red-200 text-red-800"
          }`}>
            <span>{webPrintStatus.text}</span>
          </div>
        )}
      </Surface>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <Surface className="p-4">
          <h2 className="mb-3 text-sm font-semibold text-muted-foreground">Top usuários</h2>
          <div className="space-y-2">
            {(data?.top_users ?? []).map((item) => (
              <div key={item.username} className="flex items-center justify-between border-b py-2 text-sm last:border-0 hover:bg-muted/10">
                <span className="font-medium">{item.username}</span>
                <span className="text-muted-foreground">{item.pages} pag.</span>
              </div>
            ))}
          </div>
        </Surface>
        <Surface className="p-4">
          <h2 className="mb-3 text-sm font-semibold text-muted-foreground">Top impressoras</h2>
          <div className="space-y-2">
            {(data?.top_printers ?? []).map((item) => (
              <div key={item.printer} className="flex items-center justify-between border-b py-2 text-sm last:border-0 hover:bg-muted/10">
                <span className="font-medium">{item.printer}</span>
                <span className="text-muted-foreground">{item.pages} pag.</span>
              </div>
            ))}
          </div>
        </Surface>
      </div>
      
      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <Surface className="p-4">
          <h2 className="mb-3 text-sm font-semibold text-muted-foreground">Consumo por departamento</h2>
          {(data?.department_usage ?? []).map((item) => (
            <div key={item.department} className="mb-3">
              <div className="flex justify-between text-sm mb-1">
                <span className="font-medium">{item.department}</span>
                <span className="text-muted-foreground">{item.pages} pag.</span>
              </div>
              <div className="h-2 rounded bg-muted overflow-hidden">
                <div className="h-full bg-primary transition-all duration-500" style={{ width: `${Math.min(item.pages, 100)}%` }} />
              </div>
            </div>
          ))}
        </Surface>
        <Surface className="p-4">
          <h2 className="mb-3 text-sm font-semibold text-muted-foreground">Colorido x Preto e Branco</h2>
          {(data?.color_usage ?? []).map((item) => (
            <div key={item.type} className="flex items-center justify-between border-b py-2 text-sm last:border-0 hover:bg-muted/10">
              <span className="font-medium">{item.type}</span>
              <span className="text-muted-foreground">{item.pages} pag.</span>
            </div>
          ))}
        </Surface>
      </div>
    </ProtectedPage>
  );
}
