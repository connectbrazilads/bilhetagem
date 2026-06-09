"use client";

import { useEffect, useState } from "react";
import { Download } from "lucide-react";

import { ProtectedPage } from "@/components/protected-page";
import { Button, Input, Surface } from "@/components/ui";
import { apiFetch, API_URL } from "@/lib/api";

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
      headers: { Authorization: `Bearer ${token}` }
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
    const matchUser = job.username.toLowerCase().includes(userQuery.toLowerCase());
    const matchPrinter = job.printer_name.toLowerCase().includes(printerQuery.toLowerCase());
    const matchDate = dateQuery ? job.submitted_at.startsWith(dateQuery) : true;
    return matchUser && matchPrinter && matchDate;
  });

  return (
    <ProtectedPage>
      <div className="mb-5 flex items-center justify-between">
        <h1 className="text-xl font-semibold">Relatórios</h1>
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
      
      <Surface className="grid gap-3 p-4 md:grid-cols-3 mb-4">
        <Input
          placeholder="Filtrar por Usuário"
          value={userQuery}
          onChange={(e) => setUserQuery(e.target.value)}
        />
        <Input
          placeholder="Filtrar por Impressora"
          value={printerQuery}
          onChange={(e) => setPrinterQuery(e.target.value)}
        />
        <Input
          type="date"
          value={dateQuery}
          onChange={(e) => setDateQuery(e.target.value)}
        />
      </Surface>

      <Surface className="overflow-hidden">
        <div className="p-4 border-b bg-muted/20 font-semibold text-sm">Histórico Recente de Impressões</div>
        {loading ? (
          <div className="p-8 text-center text-sm text-muted-foreground animate-pulse">Carregando histórico...</div>
        ) : filteredJobs.length === 0 ? (
          <div className="p-8 text-center text-sm text-muted-foreground">Nenhum trabalho de impressão encontrado.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-muted text-left">
                <tr>
                  <th className="p-3">Data/Hora</th>
                  <th className="p-3">Usuário</th>
                  <th className="p-3">Impressora</th>
                  <th className="p-3">Documento</th>
                  <th className="p-3">Páginas</th>
                  <th className="p-3">Cor</th>
                  <th className="p-3">Status</th>
                </tr>
              </thead>
              <tbody>
                {filteredJobs.map((job) => (
                  <tr key={job.id} className="border-t animate-fade-in">
                    <td className="p-3 text-muted-foreground whitespace-nowrap">
                      {new Date(job.submitted_at).toLocaleString("pt-BR")}
                    </td>
                    <td className="p-3 font-medium whitespace-nowrap">{job.username}</td>
                    <td className="p-3 whitespace-nowrap">{job.printer_name}</td>
                    <td className="p-3 max-w-[200px] truncate" title={job.document_name ?? "N/A"}>
                      {job.document_name ?? "N/A"}
                    </td>
                    <td className="p-3 font-medium whitespace-nowrap">{job.pages} pag.</td>
                    <td className="p-3">
                      <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${job.is_color ? "bg-purple-50 text-purple-700 border border-purple-200" : "bg-gray-100 text-gray-700 border border-gray-200"}`}>
                        {job.is_color ? "Colorida" : "P&B"}
                      </span>
                    </td>
                    <td className="p-3">
                      <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${job.status === "authorized" ? "bg-green-50 text-green-700 border border-green-200" : "bg-red-50 text-red-700 border border-red-200"}`} title={job.reason ?? undefined}>
                        {job.status === "authorized" ? "Autorizada" : "Bloqueada"}
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
