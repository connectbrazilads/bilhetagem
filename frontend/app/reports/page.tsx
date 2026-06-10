"use client";

import { Fragment, useEffect, useMemo, useState } from "react";
import { Download, FileText, Mail, Printer, Search, Users } from "lucide-react";

import { ProtectedPage } from "@/components/protected-page";
import { Button, Input, Surface } from "@/components/ui";
import { apiFetch, API_URL, getCurrentRole } from "@/lib/api";

type JobRow = {
  id: number;
  username: string;
  user_full_name: string | null;
  department_id?: number | null;
  department_name?: string | null;
  printer_name: string;
  document_name: string | null;
  pages: number;
  is_color: boolean;
  cost: number;
  status: string;
  reason: string | null;
  submitted_at: string;
  computer_name?: string | null;
  queue_name?: string | null;
  policy_name?: string | null;
  policy_action?: string | null;
};

type UserRow = {
  id: number;
  username: string;
  full_name: string;
};

type DepartmentRow = {
  id: number;
  name: string;
};

type PrinterRow = {
  id: number;
  name: string;
};

type MonthlyClosing = {
  id: number;
  year: number;
  month: number;
  total_jobs: number;
  billable_jobs: number;
  pending_jobs: number;
  blocked_jobs: number;
  total_pages: number;
  mono_pages: number;
  color_pages: number;
  blocked_pages: number;
  total_cost: number;
  snapshot: {
    totals?: {
      released_jobs?: number;
      pending_pages?: number;
    };
    by_user?: ClosingSnapshotRow[];
    by_department?: ClosingSnapshotRow[];
    by_printer?: ClosingSnapshotRow[];
    by_policy?: ClosingPolicySnapshotRow[];
  };
  generated_at: string;
};

type ClosingSnapshotRow = {
  name: string;
  jobs?: number;
  pages: number;
  cost: number;
  cost_per_page?: number;
};

type ClosingPolicySnapshotRow = {
  name: string;
  action: string;
  jobs: number;
  billable_jobs: number;
  pending_jobs: number;
  blocked_jobs: number;
  pages: number;
  saved_pages: number;
  cost: number;
};

type MonthlyClosingEmailResult = {
  sent: boolean;
  recipients: string[];
  attachments: string[];
};

type MonthlyClosingDueEmailResult = MonthlyClosingEmailResult & {
  reason: string | null;
  period: string | null;
};

export default function ReportsPage() {
  const [jobs, setJobs] = useState<JobRow[]>([]);
  const [users, setUsers] = useState<UserRow[]>([]);
  const [departments, setDepartments] = useState<DepartmentRow[]>([]);
  const [printers, setPrinters] = useState<PrinterRow[]>([]);
  const [isAdmin, setIsAdmin] = useState(false);
  const [loading, setLoading] = useState(true);
  const [userId, setUserId] = useState("");
  const [departmentId, setDepartmentId] = useState("");
  const [printerId, setPrinterId] = useState("");
  const [dateQuery, setDateQuery] = useState("");
  const now = new Date();
  const [closingYear, setClosingYear] = useState(String(now.getFullYear()));
  const [closingMonth, setClosingMonth] = useState(String(now.getMonth() + 1));
  const [closings, setClosings] = useState<MonthlyClosing[]>([]);
  const [closingError, setClosingError] = useState<string | null>(null);
  const [mailMessage, setMailMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);
  const [sendingEmailId, setSendingEmailId] = useState<number | "due" | null>(null);

  async function loadJobs() {
    const token = localStorage.getItem("token");
    if (!token) return;
    setLoading(true);
    try {
      const query = reportQueryParams();
      const data = await apiFetch<JobRow[]>(`/jobs${query ? `?${query}` : ""}`, token);
      setJobs(data);
    } catch {
      setJobs([]);
    } finally {
      setLoading(false);
    }
  }

  async function loadClosings() {
    const token = localStorage.getItem("token");
    if (!token) return;
    await apiFetch<MonthlyClosing[]>("/reports/monthly-closings", token).then(setClosings).catch(() => setClosings([]));
  }

  async function loadFilterOptions() {
    const token = localStorage.getItem("token");
    if (!token) return;
    await Promise.all([
      apiFetch<UserRow[]>("/users", token).then(setUsers).catch(() => setUsers([])),
      apiFetch<DepartmentRow[]>("/departments", token).then(setDepartments).catch(() => setDepartments([])),
      apiFetch<PrinterRow[]>("/printers", token).then(setPrinters).catch(() => setPrinters([])),
    ]);
  }

  useEffect(() => {
    const token = localStorage.getItem("token");
    setIsAdmin(token ? getCurrentRole(token) === "admin" : false);
    loadFilterOptions();
    loadJobs();
    loadClosings();
  }, []);

  function reportQueryParams() {
    const params = new URLSearchParams();
    if (userId) params.set("user_id", userId);
    if (departmentId) params.set("department_id", departmentId);
    if (printerId) params.set("printer_id", printerId);
    if (dateQuery) {
      params.set("date_from", `${dateQuery}T00:00:00`);
      params.set("date_to", `${dateQuery}T23:59:59`);
    }
    return params.toString();
  }

  async function download(format: "pdf" | "xlsx") {
    const token = localStorage.getItem("token");
    if (!token) return;
    const query = reportQueryParams();
    const response = await fetch(`${API_URL}/reports/export?format=${format}${query ? `&${query}` : ""}`, {
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

  async function generateClosing() {
    if (!isAdmin) return;
    const token = localStorage.getItem("token");
    if (!token) return;
    setClosingError(null);
    try {
      await apiFetch<MonthlyClosing>("/reports/monthly-closings", token, {
        method: "POST",
        body: JSON.stringify({ year: Number(closingYear), month: Number(closingMonth) }),
      });
      await loadClosings();
    } catch (err) {
      setClosingError(err instanceof Error ? err.message : "Falha ao gerar fechamento");
    }
  }

  async function sendClosingEmail(closing: MonthlyClosing) {
    if (!isAdmin) return;
    const token = localStorage.getItem("token");
    if (!token) return;
    setMailMessage(null);
    setSendingEmailId(closing.id);
    try {
      const result = await apiFetch<MonthlyClosingEmailResult>(`/reports/monthly-closings/${closing.id}/email`, token, {
        method: "POST",
        body: JSON.stringify({}),
      });
      setMailMessage({
        type: "success",
        text: `Fechamento ${String(closing.month).padStart(2, "0")}/${closing.year} enviado para ${result.recipients.join(", ")} com ${result.attachments.length} anexo(s).`,
      });
    } catch (err) {
      setMailMessage({ type: "error", text: err instanceof Error ? err.message : "Falha ao enviar fechamento por e-mail" });
    } finally {
      setSendingEmailId(null);
    }
  }

  async function sendDueEmail() {
    if (!isAdmin) return;
    const token = localStorage.getItem("token");
    if (!token) return;
    setMailMessage(null);
    setSendingEmailId("due");
    try {
      const result = await apiFetch<MonthlyClosingDueEmailResult>("/reports/monthly-closings/email-due", token, { method: "POST" });
      if (result.sent) {
        setMailMessage({
          type: "success",
          text: `Envio mensal realizado${result.period ? ` (${result.period})` : ""} para ${result.recipients.join(", ")}.`,
        });
        await loadClosings();
      } else {
        setMailMessage({ type: "success", text: result.reason || "Nenhum envio mensal pendente." });
      }
    } catch (err) {
      setMailMessage({ type: "error", text: err instanceof Error ? err.message : "Falha ao processar envio mensal" });
    } finally {
      setSendingEmailId(null);
    }
  }

  async function downloadClosing(closing: MonthlyClosing, format: "pdf" | "xlsx") {
    const token = localStorage.getItem("token");
    if (!token) return;
    const response = await fetch(`${API_URL}/reports/monthly-closings/${closing.id}/export?format=${format}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `fechamento-${closing.year}-${String(closing.month).padStart(2, "0")}.${format === "pdf" ? "pdf" : "xlsx"}`;
    link.click();
    URL.revokeObjectURL(url);
  }

  const summary = useMemo(() => {
    return jobs.reduce(
      (acc, job) => {
        acc.jobs += 1;
        acc.pages += job.pages;
        acc.cost += job.cost;
        acc.users.add(job.user_full_name || job.username);
        acc.printers.add(job.printer_name);
        return acc;
      },
      { jobs: 0, pages: 0, cost: 0, users: new Set<string>(), printers: new Set<string>() }
    );
  }, [jobs]);

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

      <div className="mb-4 grid gap-4 md:grid-cols-5">
        <Summary label="Trabalhos" value={summary.jobs} icon={FileText} />
        <Summary label="Paginas" value={summary.pages} icon={Printer} />
        <Summary label="Usuarios" value={summary.users.size} icon={Users} />
        <Summary label="Impressoras" value={summary.printers.size} icon={Printer} />
        <Summary label="Custo" value={`R$ ${summary.cost.toFixed(2)}`} icon={FileText} />
      </div>

      <Surface className="mb-4 grid gap-3 p-4 md:grid-cols-[1fr_1fr_1fr_180px_auto]">
        <select className="h-9 rounded-md border bg-white px-3 text-sm" value={userId} onChange={(event) => setUserId(event.target.value)}>
          <option value="">Todos usuarios</option>
          {users.map((user) => (
            <option key={user.id} value={user.id}>
              {user.full_name || user.username}
            </option>
          ))}
        </select>
        <select className="h-9 rounded-md border bg-white px-3 text-sm" value={departmentId} onChange={(event) => setDepartmentId(event.target.value)}>
          <option value="">Todos departamentos</option>
          {departments.map((department) => (
            <option key={department.id} value={department.id}>
              {department.name}
            </option>
          ))}
        </select>
        <select className="h-9 rounded-md border bg-white px-3 text-sm" value={printerId} onChange={(event) => setPrinterId(event.target.value)}>
          <option value="">Todas impressoras</option>
          {printers.map((printer) => (
            <option key={printer.id} value={printer.id}>
              {printer.name}
            </option>
          ))}
        </select>
        <Input type="date" value={dateQuery} onChange={(event) => setDateQuery(event.target.value)} />
        <Button onClick={loadJobs}>
          <Search className="h-4 w-4" />
          Filtrar
        </Button>
      </Surface>

      <Surface className="mb-4 overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b bg-muted/30 p-4">
          <div>
            <div className="text-sm font-semibold">Fechamentos mensais</div>
            <div className="text-xs text-muted-foreground">Snapshots comerciais congelados para cobranca e auditoria.</div>
          </div>
          {isAdmin ? (
            <div className="flex flex-wrap items-center gap-2">
              <Input className="w-24" type="number" value={closingYear} onChange={(event) => setClosingYear(event.target.value)} />
              <select className="h-9 rounded-md border bg-white px-3 text-sm" value={closingMonth} onChange={(event) => setClosingMonth(event.target.value)}>
                {Array.from({ length: 12 }, (_, index) => index + 1).map((month) => (
                  <option key={month} value={month}>
                    {String(month).padStart(2, "0")}
                  </option>
                ))}
              </select>
              <Button onClick={generateClosing}>Gerar fechamento</Button>
              <Button variant="outline" onClick={sendDueEmail} disabled={sendingEmailId === "due"}>
                <Mail className="h-4 w-4" />
                {sendingEmailId === "due" ? "Enviando..." : "Enviar devido"}
              </Button>
            </div>
          ) : null}
        </div>
        {closingError ? <div className="border-b border-red-200 bg-red-50 p-3 text-sm text-red-800">{closingError}</div> : null}
        {mailMessage ? (
          <div className={`border-b p-3 text-sm ${mailMessage.type === "success" ? "border-green-200 bg-green-50 text-green-800" : "border-red-200 bg-red-50 text-red-800"}`}>
            {mailMessage.text}
          </div>
        ) : null}
        {closings.length === 0 ? (
          <div className="p-6 text-center text-sm text-muted-foreground">Nenhum fechamento gerado.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-muted/80 text-left text-xs uppercase tracking-wide text-muted-foreground">
                <tr>
                  <th className="p-4">Periodo</th>
                  <th className="p-4 text-right">Paginas</th>
                  <th className="p-4 text-right">P&B</th>
                  <th className="p-4 text-right">Cor</th>
                  <th className="p-4 text-right">Custo</th>
                  <th className="p-4 text-right">Salvas</th>
                  <th className="p-4">Gerado em</th>
                  <th className="p-4 text-right">Exportar</th>
                </tr>
              </thead>
              <tbody>
                {closings.map((closing) => (
                  <Fragment key={closing.id}>
                    <tr key={`${closing.id}-row`} className="border-t bg-white hover:bg-muted/30">
                      <td className="p-4 font-semibold">{String(closing.month).padStart(2, "0")}/{closing.year}</td>
                      <td className="p-4 text-right font-semibold">{closing.total_pages.toLocaleString("pt-BR")}</td>
                      <td className="p-4 text-right">{closing.mono_pages.toLocaleString("pt-BR")}</td>
                      <td className="p-4 text-right">{closing.color_pages.toLocaleString("pt-BR")}</td>
                      <td className="p-4 text-right font-semibold">R$ {closing.total_cost.toFixed(2)}</td>
                      <td className="p-4 text-right">{closing.blocked_pages.toLocaleString("pt-BR")}</td>
                      <td className="p-4 text-muted-foreground">{new Date(closing.generated_at).toLocaleString("pt-BR")}</td>
                      <td className="p-4">
                        <div className="flex justify-end gap-2">
                          {isAdmin ? (
                            <Button variant="outline" onClick={() => sendClosingEmail(closing)} disabled={sendingEmailId === closing.id}>
                              <Mail className="h-4 w-4" />
                              {sendingEmailId === closing.id ? "..." : "E-mail"}
                            </Button>
                          ) : null}
                          <Button variant="outline" onClick={() => downloadClosing(closing, "pdf")}>PDF</Button>
                          <Button onClick={() => downloadClosing(closing, "xlsx")}>Excel</Button>
                        </div>
                      </td>
                    </tr>
                    <tr key={`${closing.id}-snapshot`} className="border-t bg-muted/20">
                      <td colSpan={8} className="p-4">
                        <div className="mb-3 flex flex-wrap gap-4 text-xs text-muted-foreground">
                          <span>{closing.billable_jobs.toLocaleString("pt-BR")} trabalho(s) cobraveis</span>
                          <span>{(closing.snapshot.totals?.released_jobs ?? 0).toLocaleString("pt-BR")} liberado(s)</span>
                          <span>{closing.pending_jobs.toLocaleString("pt-BR")} pendente(s)</span>
                          <span>{(closing.snapshot.totals?.pending_pages ?? 0).toLocaleString("pt-BR")} pag. pendente(s)</span>
                          <span>{closing.blocked_jobs.toLocaleString("pt-BR")} bloqueado(s)</span>
                        </div>
                        <div className="grid gap-4 lg:grid-cols-4">
                          <SnapshotList title="Top usuarios" rows={closing.snapshot.by_user ?? []} />
                          <SnapshotList title="Top departamentos" rows={closing.snapshot.by_department ?? []} />
                          <SnapshotList title="Top impressoras" rows={closing.snapshot.by_printer ?? []} />
                          <PolicySnapshotList rows={closing.snapshot.by_policy ?? []} />
                        </div>
                      </td>
                    </tr>
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Surface>

      <Surface className="overflow-hidden">
        <div className="border-b bg-muted/30 p-4 text-sm font-semibold">
          Historico recente <span className="text-muted-foreground">({jobs.length})</span>
        </div>
        {loading ? (
          <div className="p-8 text-center text-sm text-muted-foreground">Carregando historico...</div>
        ) : jobs.length === 0 ? (
          <div className="p-8 text-center text-sm text-muted-foreground">Nenhum trabalho encontrado.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-muted/80 text-left text-xs uppercase tracking-wide text-muted-foreground">
                <tr>
                  <th className="p-4">Data</th>
                  <th className="p-4">Usuario</th>
                  <th className="p-4">Departamento</th>
                  <th className="p-4">Impressora</th>
                  <th className="p-4">Origem</th>
                  <th className="p-4">Documento</th>
                  <th className="p-4 text-right">Paginas</th>
                  <th className="p-4 text-right">Custo</th>
                  <th className="p-4">Tipo</th>
                  <th className="p-4">Politica</th>
                  <th className="p-4">Status</th>
                </tr>
              </thead>
              <tbody>
                {jobs.map((job) => (
                  <tr key={job.id} className="border-t bg-white transition-colors hover:bg-muted/30">
                    <td className="whitespace-nowrap p-4 text-muted-foreground">{new Date(job.submitted_at).toLocaleString("pt-BR")}</td>
                    <td className="whitespace-nowrap p-4 font-semibold">{job.user_full_name || job.username}</td>
                    <td className="whitespace-nowrap p-4 text-muted-foreground">{job.department_name || "Sem departamento"}</td>
                    <td className="whitespace-nowrap p-4">{job.printer_name}</td>
                    <td className="min-w-[180px] p-4 text-xs text-muted-foreground">
                      <div>{job.computer_name ?? "-"}</div>
                      {job.queue_name && job.queue_name !== job.printer_name ? <div className="mt-0.5 font-medium text-foreground">{job.queue_name}</div> : null}
                    </td>
                    <td className="max-w-[260px] truncate p-4" title={job.document_name ?? "N/A"}>
                      {job.document_name ?? "N/A"}
                    </td>
                    <td className="whitespace-nowrap p-4 text-right font-semibold">{job.pages} pag.</td>
                    <td className="whitespace-nowrap p-4 text-right font-semibold">R$ {job.cost.toFixed(2)}</td>
                    <td className="p-4">
                      <span className={`inline-flex rounded-full border px-2 py-0.5 text-xs font-semibold ${job.is_color ? "border-purple-200 bg-purple-50 text-purple-700" : "border-slate-200 bg-slate-100 text-slate-700"}`}>
                        {job.is_color ? "Colorido" : "P&B"}
                      </span>
                    </td>
                    <td className="min-w-[180px] p-4">
                      {job.policy_name ? (
                        <div title={job.reason || job.policy_name}>
                          <span className="inline-flex rounded-full border border-blue-200 bg-blue-50 px-2 py-0.5 text-xs font-semibold text-blue-700">
                            {policyActionLabel(job.policy_action)}
                          </span>
                          <div className="mt-1 max-w-[220px] truncate text-xs font-medium" title={job.policy_name}>
                            {job.policy_name}
                          </div>
                        </div>
                      ) : (
                        <span className="text-xs text-muted-foreground">-</span>
                      )}
                    </td>
                    <td className="p-4">
                      <span
                        title={job.reason || job.policy_name || undefined}
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

function SnapshotList({ title, rows }: { title: string; rows: ClosingSnapshotRow[] }) {
  const topRows = rows.slice(0, 3);
  return (
    <div>
      <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">{title}</div>
      {topRows.length === 0 ? (
        <div className="text-sm text-muted-foreground">Sem dados.</div>
      ) : (
        <div className="space-y-2">
          {topRows.map((row) => (
            <div key={row.name} className="grid grid-cols-[1fr_auto] gap-3 text-sm">
              <span className="truncate font-medium">{row.name}</span>
              <span className="whitespace-nowrap text-right text-muted-foreground">
                {row.pages.toLocaleString("pt-BR")} pag. | R$ {row.cost.toFixed(2)}
                {typeof row.cost_per_page === "number" ? ` | R$ ${row.cost_per_page.toFixed(2)}/pag.` : ""}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function PolicySnapshotList({ rows }: { rows: ClosingPolicySnapshotRow[] }) {
  const topRows = rows.slice(0, 3);
  return (
    <div>
      <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Politicas aplicadas</div>
      {topRows.length === 0 ? (
        <div className="text-sm text-muted-foreground">Sem politicas.</div>
      ) : (
        <div className="space-y-2">
          {topRows.map((row) => (
            <div key={`${row.action}:${row.name}`} className="grid grid-cols-[1fr_auto] gap-3 text-sm">
              <span className="truncate font-medium" title={row.name}>
                {row.name}
              </span>
              <span className="whitespace-nowrap text-right text-muted-foreground">
                {policyActionLabel(row.action)} | {row.jobs.toLocaleString("pt-BR")} job(s)
                {row.saved_pages ? ` | ${row.saved_pages.toLocaleString("pt-BR")} salvas` : ""}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function statusLabel(status: string) {
  if (status === "authorized") return "Autorizada";
  if (status === "released") return "Liberada";
  if (status === "pending_release") return "Pendente";
  if (status === "cancelled") return "Cancelada";
  return "Bloqueada";
}

function policyActionLabel(action?: string | null) {
  if (action === "allow") return "Excecao";
  if (action === "block") return "Bloqueio";
  if (action === "require_release") return "Liberacao";
  if (action === "force_mono") return "Cobrar P&B";
  return "Politica";
}

function Summary({ label, value, icon: Icon }: { label: string; value: number | string; icon: typeof FileText }) {
  const displayValue = typeof value === "number" ? value.toLocaleString("pt-BR") : value;
  return (
    <Surface className="p-5">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-muted-foreground">{label}</span>
        <div className="flex h-9 w-9 items-center justify-center rounded-md bg-primary/10 text-primary">
          <Icon className="h-4 w-4" />
        </div>
      </div>
      <div className="mt-3 text-3xl font-semibold">{displayValue}</div>
    </Surface>
  );
}
