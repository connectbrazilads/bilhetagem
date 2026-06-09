"use client";

import { useEffect, useMemo, useState } from "react";
import { Download, FileText, Printer, Search, Users } from "lucide-react";

import { ProtectedPage } from "@/components/protected-page";
import { Button, Input, Surface } from "@/components/ui";
import { apiFetch, API_URL } from "@/lib/api";

type JobRow = {
  id: number;
  username: string;
  user_full_name: string | null;
  printer_name: string;
  document_name: string | null;
  pages: number;
  is_color: boolean;
  status: string;
  reason: string | null;
  submitted_at: string;
  computer_name?: string | null;
  queue_name?: string | null;
};

export default function ReportsPage() {
  const [jobs, setJobs] = useState<JobRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [userQuery, setUserQuery] = useState("");
  const [printerQuery, setPrinterQuery] = useState("");
  const [dateQuery, setDateQuery] = useState("");

  async function loadJobs() {
    const token = localStorage.getItem("token");
    if (!token) return;
    setLoading(true);
    try {
      const data = await apiFetch<JobRow[]>("/jobs", token);
      setJobs(data);
    } catch {
      setJobs([]);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadJobs();
  }, []);

  async function download(format: "pdf" | "xlsx") {
    const token = localStorage.getItem("token");
    if (!token) return;
    const response = await fetch(`${API_URL}/reports/export?format=${format}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = format === "pdf" ? "relatorio-impressoes.pdf" : "relatorio-impressoes.xlsx";
    link.click();
    URL.revokeObjectURL(url);
  }

  const filteredJobs = jobs.filter((job) => {
    const userDisplayName = job.user_full_name || job.username;
    const matchUser = `${job.username} ${userDisplayName}`.toLowerCase().includes(userQuery.toLowerCase());
    const matchPrinter = `${job.printer_name} ${job.queue_name ?? ""} ${job.computer_name ?? ""}`.toLowerCase().includes(printerQuery.toLowerCase());
    const matchDate = dateQuery ? job.submitted_at.startsWith(dateQuery) : true;
    return matchUser && matchPrinter && matchDate;
  });

  const summary = useMemo(() => {
    return filteredJobs.reduce(
      (acc, job) => {
        acc.jobs += 1;
        acc.pages += job.pages;
        acc.users.add(job.user_full_name || job.username);
        acc.printers.add(job.printer_name);
        return acc;
      },
      { jobs: 0, pages: 0, users: new Set<string>(), printers: new Set<string>() }
    );
  }, [filteredJobs]);

  return (
    <ProtectedPage>
      <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Relatorios</h1>
          <p className="mt-1 text-sm text-muted-foreground">Historico de impressoes, filtros e exportacao.</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => download("pdf")}>
            <Download className="h-4 w-4" />
            PDF
          </Button>
          <Button onClick={() => download("xlsx")}>
            <Download className="h-4 w-4" />
            Excel
          </Button>
        </div>
      </div>

      <div className="mb-4 grid gap-4 md:grid-cols-4">
        <Summary label="Trabalhos" value={summary.jobs} icon={FileText} />
        <Summary label="Paginas" value={summary.pages} icon={Printer} />
        <Summary label="Usuarios" value={summary.users.size} icon={Users} />
        <Summary label="Impressoras" value={summary.printers.size} icon={Printer} />
      </div>

      <Surface className="mb-4 grid gap-3 p-4 md:grid-cols-[1fr_1fr_220px]">
        <div className="relative">
          <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input className="pl-9" placeholder="Filtrar por usuario" value={userQuery} onChange={(event) => setUserQuery(event.target.value)} />
        </div>
        <div className="relative">
          <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input className="pl-9" placeholder="Filtrar por impressora" value={printerQuery} onChange={(event) => setPrinterQuery(event.target.value)} />
        </div>
        <Input type="date" value={dateQuery} onChange={(event) => setDateQuery(event.target.value)} />
      </Surface>

      <Surface className="overflow-hidden">
        <div className="border-b bg-muted/30 p-4 text-sm font-semibold">
          Historico recente <span className="text-muted-foreground">({filteredJobs.length})</span>
        </div>
        {loading ? (
          <div className="p-8 text-center text-sm text-muted-foreground">Carregando historico...</div>
        ) : filteredJobs.length === 0 ? (
          <div className="p-8 text-center text-sm text-muted-foreground">Nenhum trabalho encontrado.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-muted/80 text-left text-xs uppercase tracking-wide text-muted-foreground">
                <tr>
                  <th className="p-4">Data</th>
                  <th className="p-4">Usuario</th>
                  <th className="p-4">Impressora</th>
                  <th className="p-4">Origem</th>
                  <th className="p-4">Documento</th>
                  <th className="p-4 text-right">Paginas</th>
                  <th className="p-4">Tipo</th>
                  <th className="p-4">Status</th>
                </tr>
              </thead>
              <tbody>
                {filteredJobs.map((job) => (
                  <tr key={job.id} className="border-t bg-white transition-colors hover:bg-muted/30">
                    <td className="whitespace-nowrap p-4 text-muted-foreground">{new Date(job.submitted_at).toLocaleString("pt-BR")}</td>
                    <td className="whitespace-nowrap p-4 font-semibold">{job.user_full_name || job.username}</td>
                    <td className="whitespace-nowrap p-4">{job.printer_name}</td>
                    <td className="min-w-[180px] p-4 text-xs text-muted-foreground">
                      <div>{job.computer_name ?? "-"}</div>
                      {job.queue_name && job.queue_name !== job.printer_name ? <div className="mt-0.5 font-medium text-foreground">{job.queue_name}</div> : null}
                    </td>
                    <td className="max-w-[260px] truncate p-4" title={job.document_name ?? "N/A"}>
                      {job.document_name ?? "N/A"}
                    </td>
                    <td className="whitespace-nowrap p-4 text-right font-semibold">{job.pages} pag.</td>
                    <td className="p-4">
                      <span className={`inline-flex rounded-full border px-2 py-0.5 text-xs font-semibold ${job.is_color ? "border-purple-200 bg-purple-50 text-purple-700" : "border-slate-200 bg-slate-100 text-slate-700"}`}>
                        {job.is_color ? "Colorido" : "P&B"}
                      </span>
                    </td>
                    <td className="p-4">
                      <span
                        title={job.reason ?? undefined}
                        className={`inline-flex rounded-full border px-2 py-0.5 text-xs font-semibold ${
                          job.status === "authorized" || job.status === "released"
                            ? "border-green-200 bg-green-50 text-green-700"
                            : job.status === "pending_release"
                              ? "border-amber-200 bg-amber-50 text-amber-700"
                              : "border-red-200 bg-red-50 text-red-700"
                        }`}
                      >
                        {statusLabel(job.status)}
                      </span>
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

function statusLabel(status: string) {
  if (status === "authorized") return "Autorizada";
  if (status === "released") return "Liberada";
  if (status === "pending_release") return "Pendente";
  if (status === "cancelled") return "Cancelada";
  return "Bloqueada";
}

function Summary({ label, value, icon: Icon }: { label: string; value: number; icon: typeof FileText }) {
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
