"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { Activity, Building2, CircleDollarSign, Edit, FileText, KeyRound, MonitorCheck, MonitorOff, Plus } from "lucide-react";

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
    return {
      total: organizations.length,
      active: organizations.filter((organization) => organization.is_active).length,
      inactive: organizations.filter((organization) => !organization.is_active).length,
      jobs: organizations.reduce((total, organization) => total + organization.jobs_count, 0),
      jobsMonth: organizations.reduce((total, organization) => total + organization.jobs_month, 0),
      pendingJobsMonth: organizations.reduce((total, organization) => total + organization.pending_jobs_month, 0),
      blockedJobsMonth: organizations.reduce((total, organization) => total + organization.blocked_jobs_month, 0),
      onlineAgents: organizations.reduce((total, organization) => total + organization.online_agents_count, 0),
      pagesMonth: organizations.reduce((total, organization) => total + organization.pages_month, 0),
      savedPagesMonth: organizations.reduce((total, organization) => total + organization.saved_pages_month, 0),
      costMonth: organizations.reduce((total, organization) => total + organization.cost_month, 0),
    };
  }, [organizations]);

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

  return (
    <ProtectedPage roles={["admin"]}>
      <div className="mb-6">
        <h1 className="text-3xl font-bold tracking-tight">Empresas</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          {isPlatformAdmin === false ? "Acompanhe os indicadores da sua empresa neste ambiente SaaS." : "Gerencie clientes e o isolamento de dados do ambiente SaaS."}
        </p>
      </div>

      <div className="mb-4 grid gap-4 md:grid-cols-3 xl:grid-cols-10">
        <Summary label="Empresas" value={summary.total} icon={Building2} />
        <Summary label="Ativas" value={summary.active} icon={Activity} />
        <Summary label="Inativas" value={summary.inactive} icon={MonitorOff} />
        <Summary label="Agents online" value={summary.onlineAgents} icon={MonitorCheck} />
        <Summary label="Trabalhos mes" value={summary.jobsMonth} icon={FileText} />
        <Summary label="Pendentes mes" value={summary.pendingJobsMonth} icon={FileText} />
        <Summary label="Bloqueios mes" value={summary.blockedJobsMonth} icon={FileText} />
        <Summary label="Paginas mes" value={summary.pagesMonth} icon={FileText} />
        <Summary label="Salvas mes" value={summary.savedPagesMonth} icon={FileText} />
        <Summary label="Custo mes" value={money(summary.costMonth)} icon={CircleDollarSign} />
      </div>

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

function Summary({ label, value, icon: Icon }: { label: string; value: number | string; icon: typeof Building2 }) {
  return (
    <Surface className="p-5">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-muted-foreground">{label}</span>
        <div className="flex h-9 w-9 items-center justify-center rounded-md bg-primary/10 text-primary">
          <Icon className="h-4 w-4" />
        </div>
      </div>
      <div className="mt-3 text-3xl font-semibold">{typeof value === "number" ? value.toLocaleString("pt-BR") : value}</div>
    </Surface>
  );
}
