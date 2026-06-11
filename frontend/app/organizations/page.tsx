"use client";

import { FormEvent, useEffect, useMemo, useState, type ComponentType } from "react";
import { AlertTriangle, CircleDollarSign, Edit, FileText, KeyRound, MonitorCheck, MonitorOff, Plus, Printer, TrendingUp } from "lucide-react";

import { ProtectedPage } from "@/components/protected-page";
import { Button, Input, Surface } from "@/components/ui";
import { apiFetch } from "@/lib/api";

type AuthContext = {
  organization_slug: string;
};

type OrganizationRow = {
  id: number;
  name: string;
  slug: string;
  is_active: boolean;
  billing_plan: "starter" | "professional" | "enterprise";
  billing_status: "trial" | "active" | "past_due" | "suspended";
  contracted_printer_limit: number;
  created_at: string;
  users_count: number;
  printers_count: number;
  active_printers_count: number;
  contracted_printer_usage_percent: number;
  contracted_printer_limit_status: "unlimited" | "ok" | "warning" | "exceeded";
  agents_count: number;
  online_agents_count: number;
  offline_agents_count: number;
  jobs_count: number;
  jobs_month: number;
  pages_month: number;
  cost_month: number;
  pending_jobs_month: number;
  blocked_jobs_month: number;
  saved_pages_month: number;
};

const emptyForm = {
  name: "",
  slug: "",
  is_active: true,
  billing_plan: "starter",
  billing_status: "trial",
  contracted_printer_limit: 0,
  admin_username: "admin",
  admin_password: "",
  agent_username: "agent",
  agent_password: "",
};

const UNSAFE_INITIAL_PASSWORDS = new Set([
  "",
  "admin",
  "agent",
  "admin12345",
  "agent12345",
  "change-me-admin-password",
  "change-me-agent-password",
  "password",
  "senha123",
  "12345678",
]);

export default function OrganizationsPage() {
  const [organizations, setOrganizations] = useState<OrganizationRow[]>([]);
  const [form, setForm] = useState(emptyForm);
  const [editing, setEditing] = useState<OrganizationRow | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isPlatformAdmin, setIsPlatformAdmin] = useState<boolean | null>(null);

  async function load() {
    const token = localStorage.getItem("token");
    if (!token) return;
    await apiFetch<OrganizationRow[]>("/organizations", token).then(setOrganizations).catch(() => setOrganizations([]));
  }

  useEffect(() => {
    const token = localStorage.getItem("token");
    if (token) {
      apiFetch<AuthContext>("/auth/me", token)
        .then((context) => setIsPlatformAdmin(context.organization_slug === "default"))
        .catch(() => setIsPlatformAdmin(localStorage.getItem("organization_slug") === "default"));
    }
    load();
  }, []);

  const summary = useMemo(() => {
    const active = organizations.filter((organization) => organization.is_active).length;
    return {
      total: organizations.length,
      active,
      inactive: organizations.length - active,
      trial: organizations.filter((organization) => organization.billing_status === "trial").length,
      pastDue: organizations.filter((organization) => organization.billing_status === "past_due").length,
      suspended: organizations.filter((organization) => organization.billing_status === "suspended").length,
      printerLimitAlerts: organizations.filter((organization) => organization.contracted_printer_limit_status === "warning" || organization.contracted_printer_limit_status === "exceeded").length,
      activePrinters: organizations.reduce((total, organization) => total + organization.active_printers_count, 0),
      jobs: organizations.reduce((total, organization) => total + organization.jobs_count, 0),
      jobsMonth: organizations.reduce((total, organization) => total + organization.jobs_month, 0),
      pendingJobsMonth: organizations.reduce((total, organization) => total + organization.pending_jobs_month, 0),
      blockedJobsMonth: organizations.reduce((total, organization) => total + organization.blocked_jobs_month, 0),
      totalAgents: organizations.reduce((total, organization) => total + organization.agents_count, 0),
      onlineAgents: organizations.reduce((total, organization) => total + organization.online_agents_count, 0),
      offlineAgents: organizations.reduce((total, organization) => total + organization.offline_agents_count, 0),
      pagesMonth: organizations.reduce((total, organization) => total + organization.pages_month, 0),
      savedPagesMonth: organizations.reduce((total, organization) => total + organization.saved_pages_month, 0),
      costMonth: organizations.reduce((total, organization) => total + organization.cost_month, 0),
    };
  }, [organizations]);
  const activePercent = summary.total ? Math.round((summary.active / summary.total) * 100) : 0;
  const agentOnlinePercent = summary.totalAgents ? Math.round((summary.onlineAgents / summary.totalAgents) * 100) : 0;
  const commercialAlerts = summary.pastDue + summary.suspended + summary.printerLimitAlerts;

  async function submit(event: FormEvent) {
    event.preventDefault();
    const token = localStorage.getItem("token");
    if (!token) return;
    setError(null);
    try {
      if (editing) {
        await apiFetch<OrganizationRow>(`/organizations/${editing.id}`, token, {
          method: "PUT",
          body: JSON.stringify({
            name: form.name,
            is_active: form.is_active,
            billing_plan: form.billing_plan,
            billing_status: form.billing_status,
            contracted_printer_limit: Number(form.contracted_printer_limit) || 0,
          }),
        });
      } else {
        const passwordError = validateInitialPasswords(form.admin_password, form.agent_password);
        if (passwordError) {
          setError(passwordError);
          return;
        }
        await apiFetch<OrganizationRow>("/organizations", token, {
          method: "POST",
          body: JSON.stringify({ ...form, contracted_printer_limit: Number(form.contracted_printer_limit) || 0 }),
        });
      }
      setEditing(null);
      setForm(emptyForm);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao salvar empresa");
    }
  }

  function startEdit(organization: OrganizationRow) {
    setEditing(organization);
    setForm({
      ...emptyForm,
      name: organization.name,
      slug: organization.slug,
      is_active: organization.is_active,
      billing_plan: organization.billing_plan,
      billing_status: organization.billing_status,
      contracted_printer_limit: organization.contracted_printer_limit,
    });
  }

  function resetForm() {
    setEditing(null);
    setForm(emptyForm);
  }

  function fillPassword(field: "admin_password" | "agent_password") {
    setForm((current) => ({ ...current, [field]: generatePassword() }));
  }

  const adminPasswordWarning =
    !editing && form.admin_password && isUnsafeInitialPassword(form.admin_password)
      ? "Senha padrao ou placeholder bloqueado."
      : null;
  const agentPasswordWarning =
    !editing && form.agent_password && isUnsafeInitialPassword(form.agent_password)
      ? "Senha padrao ou placeholder bloqueado."
      : null;
  const sharedPasswordWarning =
    !editing && form.admin_password && form.agent_password && form.admin_password.trim() === form.agent_password.trim()
      ? "Admin e agent precisam ter senhas diferentes."
      : null;

  return (
    <ProtectedPage roles={["admin"]}>
      <div className="mb-6">
        <h1 className="text-3xl font-bold tracking-tight">Empresas</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          {isPlatformAdmin === false ? "Acompanhe os indicadores da sua empresa neste ambiente SaaS." : "Gerencie clientes e o isolamento de dados do ambiente SaaS."}
        </p>
      </div>

      <Surface className="mb-6 overflow-hidden">
        <div className="grid gap-0 lg:grid-cols-[1.15fr_0.85fr]">
          <div className="border-b p-5 lg:border-b-0 lg:border-r">
            <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
              <div>
                <div className="text-xs font-bold uppercase text-muted-foreground">Centro SaaS</div>
                <div className="mt-1 text-xl font-bold">Carteira de empresas</div>
              </div>
              <span className={`inline-flex rounded-full border px-2.5 py-1 text-xs font-bold ${commercialAlerts || summary.inactive ? "border-amber-200 bg-amber-50 text-amber-700" : "border-emerald-200 bg-emerald-50 text-emerald-700"}`}>
                {commercialAlerts || summary.inactive ? "Requer acompanhamento" : "Carteira saudavel"}
              </span>
            </div>
            <div className="mb-3 flex flex-wrap items-end gap-3">
              <div className="text-4xl font-bold">{activePercent}%</div>
              <div className="pb-1 text-sm text-muted-foreground">
                {summary.active.toLocaleString("pt-BR")} de {summary.total.toLocaleString("pt-BR")} empresa(s) ativas
              </div>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-slate-100">
              <div className="h-full rounded-full bg-emerald-500" style={{ width: `${activePercent}%` }} />
            </div>
            <div className="mt-4 grid gap-2 sm:grid-cols-3">
              <OrgSignal icon={CircleDollarSign} label="Custo mensal" value={money(summary.costMonth)} detail={`${summary.pagesMonth.toLocaleString("pt-BR")} paginas no mes`} />
              <OrgSignal icon={MonitorCheck} label="Agents online" value={`${agentOnlinePercent}%`} detail={`${summary.onlineAgents}/${summary.totalAgents} agent(s)`} />
              <OrgSignal icon={Printer} label="Impressoras" value={summary.activePrinters.toLocaleString("pt-BR")} detail="Equipamentos ativos" />
            </div>
          </div>
          <div className="grid gap-0 sm:grid-cols-2">
            <OrgTile icon={AlertTriangle} label="Comercial" value={commercialAlerts} detail={`${summary.pastDue} atraso, ${summary.suspended} suspensa, ${summary.printerLimitAlerts} limite`} tone={commercialAlerts ? "warn" : "ok"} />
            <OrgTile icon={MonitorOff} label="Offline" value={summary.offlineAgents} detail="Agents sem contato" tone={summary.offlineAgents ? "danger" : "ok"} />
            <OrgTile icon={FileText} label="Jobs mes" value={summary.jobsMonth} detail={`${summary.pendingJobsMonth} pend., ${summary.blockedJobsMonth} bloq.`} tone={summary.pendingJobsMonth || summary.blockedJobsMonth ? "warn" : "info"} />
            <OrgTile icon={TrendingUp} label="Pag. salvas" value={summary.savedPagesMonth} detail="Economia por bloqueios/cancelamentos" tone={summary.savedPagesMonth ? "ok" : "muted"} />
          </div>
        </div>
      </Surface>

      {isPlatformAdmin === true ? (
        <Surface as="form" className="mb-4 p-4" onSubmit={submit}>
          <div className="grid gap-3 lg:grid-cols-[1fr_180px_160px_160px_140px_auto]">
            <Input
              placeholder="Nome da empresa"
              value={form.name}
              onChange={(event) => setForm({ ...form, name: event.target.value })}
              required
            />
            <Input
              placeholder="slug-da-empresa"
              value={form.slug}
              onChange={(event) => setForm({ ...form, slug: event.target.value.toLowerCase().replace(/\s+/g, "-") })}
              required
              disabled={editing !== null}
            />
            <select
              value={form.billing_plan}
              onChange={(event) => setForm({ ...form, billing_plan: event.target.value as typeof form.billing_plan })}
              className="h-9 rounded-md border bg-white px-3 text-sm outline-none focus-visible:border-primary focus-visible:ring-2 focus-visible:ring-ring/20"
            >
              <option value="starter">Starter</option>
              <option value="professional">Professional</option>
              <option value="enterprise">Enterprise</option>
            </select>
            <select
              value={form.billing_status}
              onChange={(event) => setForm({ ...form, billing_status: event.target.value as typeof form.billing_status })}
              className="h-9 rounded-md border bg-white px-3 text-sm outline-none focus-visible:border-primary focus-visible:ring-2 focus-visible:ring-ring/20"
            >
              <option value="trial">Teste</option>
              <option value="active">Em dia</option>
              <option value="past_due">Em atraso</option>
              <option value="suspended">Suspenso</option>
            </select>
            <Input
              type="number"
              min={0}
              placeholder="Limite imp."
              value={form.contracted_printer_limit}
              onChange={(event) => setForm({ ...form, contracted_printer_limit: parseInt(event.target.value) || 0 })}
            />
            <div className="flex flex-wrap items-center gap-2">
              {editing ? (
                <label className="flex items-center gap-2 px-2 text-sm font-medium">
                  <input
                    type="checkbox"
                    className="h-4 w-4 rounded border-gray-300 text-primary focus:ring-primary"
                    checked={form.is_active}
                    onChange={(event) => setForm({ ...form, is_active: event.target.checked })}
                  />
                  Ativa
                </label>
              ) : null}
              <Button type="submit">
                <Plus className="h-4 w-4" />
                {editing ? "Salvar" : "Cadastrar"}
              </Button>
              {editing ? (
                <Button type="button" variant="outline" onClick={resetForm}>
                  Cancelar
                </Button>
              ) : null}
            </div>
          </div>

          {!editing ? (
            <div className="mt-4 grid gap-3 border-t pt-4 md:grid-cols-2 lg:grid-cols-4">
              <label className="grid gap-1.5 text-xs font-semibold text-muted-foreground">
                Admin inicial
                <Input value={form.admin_username} onChange={(event) => setForm({ ...form, admin_username: event.target.value })} required />
              </label>
              <label className="grid gap-1.5 text-xs font-semibold text-muted-foreground">
                <span className="flex items-center justify-between gap-2">
                  Senha do admin
                  <Button type="button" variant="outline" className="h-7 px-2 text-xs" onClick={() => fillPassword("admin_password")} title="Gerar senha forte para o admin">
                    <KeyRound className="h-3.5 w-3.5" />
                    Gerar
                  </Button>
                </span>
                <Input type="password" value={form.admin_password} onChange={(event) => setForm({ ...form, admin_password: event.target.value })} required minLength={8} autoComplete="new-password" />
                {adminPasswordWarning || sharedPasswordWarning ? <span className="text-xs font-medium text-red-700">{adminPasswordWarning || sharedPasswordWarning}</span> : null}
              </label>
              <label className="grid gap-1.5 text-xs font-semibold text-muted-foreground">
                Usuario do agent
                <Input value={form.agent_username} onChange={(event) => setForm({ ...form, agent_username: event.target.value })} required />
              </label>
              <label className="grid gap-1.5 text-xs font-semibold text-muted-foreground">
                <span className="flex items-center justify-between gap-2">
                  Senha do agent
                  <Button type="button" variant="outline" className="h-7 px-2 text-xs" onClick={() => fillPassword("agent_password")} title="Gerar senha forte para o agent">
                    <KeyRound className="h-3.5 w-3.5" />
                    Gerar
                  </Button>
                </span>
                <Input type="password" value={form.agent_password} onChange={(event) => setForm({ ...form, agent_password: event.target.value })} required minLength={8} autoComplete="new-password" />
                {agentPasswordWarning || sharedPasswordWarning ? <span className="text-xs font-medium text-red-700">{agentPasswordWarning || sharedPasswordWarning}</span> : null}
              </label>
            </div>
          ) : null}
        </Surface>
      ) : isPlatformAdmin === false ? (
        <Surface className="mb-4 border-blue-100 bg-blue-50/60 p-4 text-sm text-blue-900">
          Esta visao mostra apenas a empresa vinculada ao seu login. Criacao e ativacao de clientes ficam restritas ao admin da plataforma.
        </Surface>
      ) : null}

      {error ? <Surface className="mb-4 border-red-200 bg-red-50 p-3 text-sm text-red-800">{error}</Surface> : null}

      <Surface className="overflow-hidden">
        <div className="border-b bg-muted/30 p-4 text-sm font-semibold">
          Empresas cadastradas <span className="text-muted-foreground">({organizations.length})</span>
        </div>
        {organizations.length === 0 ? (
          <div className="p-8 text-center text-sm text-muted-foreground">Nenhuma empresa encontrada.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-muted/80 text-left text-xs uppercase tracking-wide text-muted-foreground">
                <tr>
                  <th className="p-4">Empresa</th>
                  <th className="p-4">Slug</th>
                  <th className="p-4">Comercial</th>
                  <th className="p-4">Uso</th>
                  <th className="p-4">Criada em</th>
                  <th className="p-4">Status</th>
                  <th className="p-4 text-right">Acoes</th>
                </tr>
              </thead>
              <tbody>
                {organizations.map((organization) => (
                  <tr key={organization.id} className="border-t bg-white transition-colors hover:bg-muted/30">
                    <td className="p-4 font-semibold">{organization.name}</td>
                    <td className="p-4 font-mono text-xs text-muted-foreground">{organization.slug}</td>
                    <td className="p-4">
                      <div className="flex flex-wrap gap-1.5">
                        <span className="inline-flex rounded-full border bg-muted/40 px-2 py-0.5 text-xs font-semibold text-muted-foreground">
                          {planLabel(organization.billing_plan)}
                        </span>
                        <span className={`inline-flex rounded-full border px-2 py-0.5 text-xs font-semibold ${billingStatusClass(organization.billing_status)}`}>
                          {billingStatusLabel(organization.billing_status)}
                        </span>
                        <span className={`inline-flex rounded-full border px-2 py-0.5 text-xs font-semibold ${printerLimitClass(organization.contracted_printer_limit_status)}`}>
                          {printerLimitLabel(organization)}
                        </span>
                      </div>
                    </td>
                    <td className="p-4">
                      <div className="flex flex-wrap gap-1.5">
                        <MetricPill label="Usuarios" value={organization.users_count} />
                        <MetricPill label="Impressoras" value={organization.printers_count} />
                        <MetricPill label="Ativas" value={organization.active_printers_count} tone={organization.contracted_printer_limit_status === "exceeded" ? "danger" : organization.contracted_printer_limit_status === "warning" ? "warning" : "muted"} />
                        <MetricPill label="Agents" value={organization.agents_count} />
                        <MetricPill label="Online" value={organization.online_agents_count} tone="success" />
                        <MetricPill label="Offline" value={organization.offline_agents_count} tone={organization.offline_agents_count > 0 ? "danger" : "muted"} />
                        <MetricPill label="Jobs" value={organization.jobs_count} />
                        <MetricPill label="Jobs mes" value={organization.jobs_month} />
                        <MetricPill label="Pend. mes" value={organization.pending_jobs_month} tone={organization.pending_jobs_month > 0 ? "warning" : "muted"} />
                        <MetricPill label="Bloq. mes" value={organization.blocked_jobs_month} tone={organization.blocked_jobs_month > 0 ? "danger" : "muted"} />
                        <MetricPill label="Pag. mes" value={organization.pages_month} />
                        <MetricPill label="Salvas mes" value={organization.saved_pages_month} tone={organization.saved_pages_month > 0 ? "success" : "muted"} />
                        <span className="inline-flex rounded-full border bg-muted/40 px-2 py-0.5 text-xs font-semibold text-muted-foreground">
                          {money(organization.cost_month)} mes
                        </span>
                        {organization.pages_month > 0 ? (
                          <span className="inline-flex rounded-full border bg-muted/40 px-2 py-0.5 text-xs font-semibold text-muted-foreground">
                            {money(organization.cost_month / organization.pages_month)} / pag.
                          </span>
                        ) : null}
                      </div>
                    </td>
                    <td className="p-4 text-muted-foreground">{new Date(organization.created_at).toLocaleDateString("pt-BR")}</td>
                    <td className="p-4">
                      <span className={`inline-flex rounded-full border px-2 py-0.5 text-xs font-semibold ${organization.is_active ? "border-green-200 bg-green-50 text-green-700" : "border-red-200 bg-red-50 text-red-700"}`}>
                        {organization.is_active ? "Ativa" : "Inativa"}
                      </span>
                    </td>
                    <td className="p-4 text-right">
                      {isPlatformAdmin === true ? (
                        <Button variant="ghost" onClick={() => startEdit(organization)} title="Editar" className="h-8 w-8 p-0">
                          <Edit className="h-4 w-4 text-muted-foreground hover:text-foreground" />
                        </Button>
                      ) : isPlatformAdmin === false ? (
                        <span className="text-xs text-muted-foreground">Somente leitura</span>
                      ) : null}
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

function money(value: number) {
  return value.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

function planLabel(plan: OrganizationRow["billing_plan"]) {
  const labels = {
    starter: "Starter",
    professional: "Professional",
    enterprise: "Enterprise",
  };
  return labels[plan] || plan;
}

function billingStatusLabel(status: OrganizationRow["billing_status"]) {
  const labels = {
    trial: "Teste",
    active: "Em dia",
    past_due: "Em atraso",
    suspended: "Suspenso",
  };
  return labels[status] || status;
}

function billingStatusClass(status: OrganizationRow["billing_status"]) {
  if (status === "active") return "border-green-200 bg-green-50 text-green-700";
  if (status === "past_due") return "border-amber-200 bg-amber-50 text-amber-700";
  if (status === "suspended") return "border-red-200 bg-red-50 text-red-700";
  return "border-blue-200 bg-blue-50 text-blue-700";
}

function printerLimitLabel(organization: OrganizationRow) {
  if (organization.contracted_printer_limit <= 0) return "Sem limite";
  return `${organization.active_printers_count}/${organization.contracted_printer_limit} ativas (${organization.contracted_printer_usage_percent}%)`;
}

function printerLimitClass(status: OrganizationRow["contracted_printer_limit_status"]) {
  if (status === "ok") return "border-green-200 bg-green-50 text-green-700";
  if (status === "warning") return "border-amber-200 bg-amber-50 text-amber-700";
  if (status === "exceeded") return "border-red-200 bg-red-50 text-red-700";
  return "bg-muted/40 text-muted-foreground";
}

function validateInitialPasswords(adminPassword: string, agentPassword: string) {
  if (isUnsafeInitialPassword(adminPassword)) {
    return "Use uma senha forte e exclusiva para o admin inicial; senhas padrao ou placeholders sao bloqueadas.";
  }
  if (isUnsafeInitialPassword(agentPassword)) {
    return "Use uma senha forte e exclusiva para o agent; senhas padrao ou placeholders sao bloqueadas.";
  }
  if (adminPassword.trim() === agentPassword.trim()) {
    return "Use senhas diferentes para admin e agent.";
  }
  return null;
}

function isUnsafeInitialPassword(value: string) {
  return UNSAFE_INITIAL_PASSWORDS.has(value.trim().toLowerCase());
}

function generatePassword(length = 18) {
  const groups = ["ABCDEFGHJKLMNPQRSTUVWXYZ", "abcdefghijkmnopqrstuvwxyz", "23456789", "!@#$%*?"];
  const all = groups.join("");
  const chars = groups.map((group) => pickChar(group));
  while (chars.length < length) {
    chars.push(pickChar(all));
  }
  return shuffle(chars).join("");
}

function pickChar(source: string) {
  const index = secureRandom(source.length);
  return source[index];
}

function secureRandom(max: number) {
  const cryptoApi = typeof crypto !== "undefined" ? crypto : null;
  if (cryptoApi?.getRandomValues) {
    const values = new Uint32Array(1);
    cryptoApi.getRandomValues(values);
    return values[0] % max;
  }
  return Math.floor(Math.random() * max);
}

function shuffle(values: string[]) {
  const result = [...values];
  for (let index = result.length - 1; index > 0; index -= 1) {
    const swapIndex = secureRandom(index + 1);
    [result[index], result[swapIndex]] = [result[swapIndex], result[index]];
  }
  return result;
}

function MetricPill({ label, value, tone = "muted" }: { label: string; value: number; tone?: "muted" | "success" | "warning" | "danger" }) {
  const toneClass =
    tone === "success"
      ? "border-emerald-200 bg-emerald-50 text-emerald-700"
      : tone === "warning"
        ? "border-amber-200 bg-amber-50 text-amber-700"
      : tone === "danger"
        ? "border-red-200 bg-red-50 text-red-700"
        : "bg-muted/40 text-muted-foreground";
  return (
    <span className={`inline-flex rounded-full border px-2 py-0.5 text-xs font-semibold ${toneClass}`}>
      {value.toLocaleString("pt-BR")} {label}
    </span>
  );
}

function OrgSignal({
  icon: Icon,
  label,
  value,
  detail,
}: {
  icon: ComponentType<{ className?: string }>;
  label: string;
  value: string;
  detail: string;
}) {
  return (
    <div className="rounded-md border border-slate-200 bg-slate-50 p-3">
      <div className="mb-2 flex items-center justify-between gap-3">
        <div className="text-[11px] font-bold uppercase text-muted-foreground">{label}</div>
        <Icon className="h-4 w-4 text-primary" />
      </div>
      <div className="text-lg font-bold">{value}</div>
      <div className="mt-1 text-xs text-muted-foreground">{detail}</div>
    </div>
  );
}

function OrgTile({
  icon: Icon,
  label,
  value,
  detail,
  tone,
}: {
  icon: ComponentType<{ className?: string }>;
  label: string;
  value: number;
  detail: string;
  tone: "ok" | "warn" | "danger" | "info" | "muted";
}) {
  const toneClass =
    tone === "ok"
      ? "border-emerald-200 bg-emerald-50 text-emerald-700"
      : tone === "warn"
      ? "border-amber-200 bg-amber-50 text-amber-700"
      : tone === "danger"
      ? "border-red-200 bg-red-50 text-red-700"
      : tone === "info"
      ? "border-blue-200 bg-blue-50 text-blue-700"
      : "border-slate-200 bg-slate-50 text-slate-700";

  return (
    <div className="border-b p-4 sm:border-r odd:sm:border-r">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div className="text-xs font-bold uppercase text-muted-foreground">{label}</div>
        <span className={`flex h-8 w-8 items-center justify-center rounded-md border ${toneClass}`}>
          <Icon className="h-4 w-4" />
        </span>
      </div>
      <div className="text-2xl font-bold">{value.toLocaleString("pt-BR")}</div>
      <div className="mt-1 text-xs leading-5 text-muted-foreground">{detail}</div>
    </div>
  );
}
