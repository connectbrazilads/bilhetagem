"use client";

import { FormEvent, useEffect, useMemo, useState, type ComponentType } from "react";
import { AlertTriangle, Building2, Edit, MonitorCog, Plus, ShieldCheck, Trash2, UserCog, Users, WalletCards } from "lucide-react";

import { ProtectedPage } from "@/components/protected-page";
import { Button, Input, Surface } from "@/components/ui";
import { apiFetch, getCurrentRole } from "@/lib/api";

type UserRow = {
  id: number;
  username: string;
  full_name: string;
  role: string;
  department_id: number | null;
  department_name: string | null;
  is_active: boolean;
  monthly_limit: number | null;
  monthly_balance: number | null;
  used_balance: number | null;
};

type DepartmentRow = {
  id: number;
  name: string;
  cost_center: string | null;
  created_at: string;
};

const emptyForm = {
  username: "",
  full_name: "",
  password: "",
  role: "user",
  department_id: "",
  monthly_limit: "500",
  monthly_balance: "50.00",
  is_active: true,
};

const emptyDepartmentForm = {
  name: "",
  cost_center: "",
};

const humanRoleOptions = [
  { value: "user", label: "Usuario" },
  { value: "manager", label: "Gestor" },
  { value: "admin", label: "Administrador" },
];

export default function UsersPage() {
  const [users, setUsers] = useState<UserRow[]>([]);
  const [departments, setDepartments] = useState<DepartmentRow[]>([]);
  const [form, setForm] = useState(emptyForm);
  const [departmentForm, setDepartmentForm] = useState(emptyDepartmentForm);
  const [error, setError] = useState<string | null>(null);
  const [departmentError, setDepartmentError] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editingDepartmentId, setEditingDepartmentId] = useState<number | null>(null);
  const [showBalance, setShowBalance] = useState(true);
  const [isAdmin, setIsAdmin] = useState(false);
  const editingUser = useMemo(() => users.find((user) => user.id === editingId) ?? null, [users, editingId]);
  const editingAgent = editingUser?.role === "agent";
  const creatingPanelUser = editingId === null && ["admin", "manager"].includes(form.role);
  const editingPanelTarget = editingId !== null && !editingAgent && ["admin", "manager"].includes(form.role);
  const editingPasswordUser = editingId !== null && (editingAgent || editingPanelTarget);
  const showPasswordField = creatingPanelUser || editingPasswordUser;

  async function load() {
    const token = localStorage.getItem("token");
    if (!token) return;
    await Promise.all([
      apiFetch<UserRow[]>("/users", token).then(setUsers).catch(() => setUsers([])),
      apiFetch<DepartmentRow[]>("/departments", token).then(setDepartments).catch(() => setDepartments([])),
    ]);

    try {
      const settingsData = await apiFetch<{ show_balance: boolean }>("/settings", token);
      setShowBalance(settingsData.show_balance);
    } catch {
      setShowBalance(true);
    }
  }

  useEffect(() => {
    const token = localStorage.getItem("token");
    setIsAdmin(token ? getCurrentRole(token) === "admin" : false);
    load();
  }, []);

  const summary = useMemo(() => {
    const active = users.filter((user) => user.is_active).length;
    return {
      total: users.length,
      active,
      inactive: users.length - active,
      admins: users.filter((user) => user.role === "admin").length,
      managers: users.filter((user) => user.role === "manager").length,
      agents: users.filter((user) => user.role === "agent").length,
      panelUsers: users.filter((user) => user.role === "admin" || user.role === "manager").length,
      withoutDepartment: users.filter((user) => user.role !== "agent" && !user.department_id).length,
      totalLimit: users.reduce((total, user) => total + (user.monthly_limit ?? 0), 0),
      totalBalance: users.reduce((total, user) => total + (user.monthly_balance ?? 0), 0),
      usedBalance: users.reduce((total, user) => total + (user.used_balance ?? 0), 0),
      departments: departments.length,
    };
  }, [users, departments]);
  const activePercent = summary.total ? Math.round((summary.active / summary.total) * 100) : 0;
  const humanUsers = Math.max(summary.total - summary.agents, 0);
  const departmentCoveragePercent = humanUsers ? Math.round(((humanUsers - summary.withoutDepartment) / humanUsers) * 100) : 0;

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!isAdmin) return;
    const token = localStorage.getItem("token");
    if (!token) return;
    setError(null);
    if (!editingId && ["admin", "manager"].includes(form.role) && !form.password.trim()) {
      setError("Informe uma senha para usuarios com acesso ao painel.");
      return;
    }
    if (editingId && editingUser?.role === "user" && ["admin", "manager"].includes(form.role) && !form.password.trim()) {
      setError("Informe uma senha para promover o usuario ao painel.");
      return;
    }
    try {
      if (editingId) {
        await apiFetch<UserRow>(`/users/${editingId}`, token, {
          method: "PUT",
          body: JSON.stringify({
            full_name: form.full_name,
            ...(form.password.trim() ? { password: form.password.trim() } : {}),
            ...(!editingAgent ? { role: form.role } : {}),
            department_id: form.department_id ? Number(form.department_id) : null,
            monthly_limit: Number(form.monthly_limit),
            monthly_balance: Number(form.monthly_balance),
            is_active: form.is_active,
          }),
        });
        setEditingId(null);
      } else {
        await apiFetch<UserRow>("/users", token, {
          method: "POST",
          body: JSON.stringify({
            username: form.username,
            full_name: form.full_name,
            department_id: form.department_id ? Number(form.department_id) : null,
            monthly_limit: Number(form.monthly_limit),
            monthly_balance: Number(form.monthly_balance),
            role: form.role,
            ...(form.password.trim() ? { password: form.password.trim() } : {}),
          }),
        });
      }
      setForm(emptyForm);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao salvar usuario");
    }
  }

  function startEdit(user: UserRow) {
    if (!isAdmin) return;
    setEditingId(user.id);
    setForm({
      username: user.username,
      full_name: user.full_name,
      password: "",
      role: user.role,
      department_id: user.department_id?.toString() ?? "",
      monthly_limit: String(user.monthly_limit ?? 500),
      monthly_balance: String(user.monthly_balance ?? 50.0),
      is_active: user.is_active,
    });
  }

  function resetForm() {
    setEditingId(null);
    setForm(emptyForm);
  }

  async function submitDepartment(event: FormEvent) {
    event.preventDefault();
    if (!isAdmin) return;
    const token = localStorage.getItem("token");
    if (!token) return;
    setDepartmentError(null);
    try {
      if (editingDepartmentId) {
        await apiFetch<DepartmentRow>(`/departments/${editingDepartmentId}`, token, {
          method: "PUT",
          body: JSON.stringify({ name: departmentForm.name, cost_center: departmentForm.cost_center || null }),
        });
      } else {
        await apiFetch<DepartmentRow>("/departments", token, {
          method: "POST",
          body: JSON.stringify({ name: departmentForm.name, cost_center: departmentForm.cost_center || null }),
        });
      }
      resetDepartmentForm();
      await load();
    } catch (err) {
      setDepartmentError(err instanceof Error ? err.message : "Falha ao salvar departamento");
    }
  }

  function startEditDepartment(department: DepartmentRow) {
    if (!isAdmin) return;
    setEditingDepartmentId(department.id);
    setDepartmentForm({ name: department.name, cost_center: department.cost_center ?? "" });
  }

  function resetDepartmentForm() {
    setEditingDepartmentId(null);
    setDepartmentForm(emptyDepartmentForm);
  }

  async function deleteDepartment(department: DepartmentRow) {
    if (!isAdmin) return;
    const confirmed = window.confirm(`Excluir o departamento "${department.name}"?`);
    if (!confirmed) return;
    const token = localStorage.getItem("token");
    if (!token) return;
    setDepartmentError(null);
    try {
      await apiFetch<{ status: string }>(`/departments/${department.id}`, token, { method: "DELETE" });
      if (editingDepartmentId === department.id) resetDepartmentForm();
      await load();
    } catch (err) {
      setDepartmentError(err instanceof Error ? err.message : "Falha ao excluir departamento");
    }
  }

  async function deleteUser(user: UserRow) {
    if (!isAdmin) return;
    if (user.username === "admin" || user.username === "agent") {
      setError("Usuarios protegidos nao podem ser excluidos.");
      return;
    }
    const confirmed = window.confirm(
      user.role === "agent"
        ? `Excluir o agent tecnico "${user.username}"? Reinstalacoes futuras do mesmo PC vao reutilizar apenas um cadastro.`
        : `Excluir o usuario "${user.full_name || user.username}"? Usuarios com historico devem ser desativados para preservar relatorios.`,
    );
    if (!confirmed) return;
    const token = localStorage.getItem("token");
    if (!token) return;
    setError(null);
    try {
      await apiFetch<{ status: string; deleted_jobs: number }>(`/users/${user.id}`, token, { method: "DELETE" });
      if (editingId === user.id) resetForm();
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao excluir usuario");
    }
  }

  return (
    <ProtectedPage>
      <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Usuarios</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {isAdmin ? "Cadastre usuarios, departamentos e limites de impressao." : "Consulte usuarios, departamentos e limites de impressao."}
          </p>
        </div>
      </div>

      <Surface className="mb-6 overflow-hidden">
        <div className="grid gap-0 lg:grid-cols-[1.15fr_0.85fr]">
          <div className="border-b p-5 lg:border-b-0 lg:border-r">
            <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
              <div>
                <div className="text-xs font-bold uppercase text-muted-foreground">Diretorio operacional</div>
                <div className="mt-1 text-xl font-bold">Usuarios, acessos e centros de custo</div>
              </div>
              <span className={`inline-flex rounded-full border px-2.5 py-1 text-xs font-bold ${summary.inactive || summary.withoutDepartment ? "border-amber-200 bg-amber-50 text-amber-700" : "border-emerald-200 bg-emerald-50 text-emerald-700"}`}>
                {summary.inactive || summary.withoutDepartment ? "Revisar cadastros" : "Base organizada"}
              </span>
            </div>
            <div className="mb-3 flex flex-wrap items-end gap-3">
              <div className="text-4xl font-bold">{activePercent}%</div>
              <div className="pb-1 text-sm text-muted-foreground">
                {summary.active.toLocaleString("pt-BR")} de {summary.total.toLocaleString("pt-BR")} usuario(s) ativos
              </div>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-slate-100">
              <div className="h-full rounded-full bg-emerald-500" style={{ width: `${activePercent}%` }} />
            </div>
            <div className="mt-4 grid gap-2 sm:grid-cols-3">
              <UserSignal icon={Building2} label="Cobertura depto." value={`${departmentCoveragePercent}%`} detail={`${summary.departments} departamento(s)`} />
              <UserSignal icon={WalletCards} label="Limite total" value={`${summary.totalLimit.toLocaleString("pt-BR")} pag.`} detail={showBalance ? `${money(summary.totalBalance)} em saldo` : "Saldo oculto nas telas"} />
              <UserSignal icon={Users} label="Humanos" value={humanUsers.toLocaleString("pt-BR")} detail={`${summary.agents} tecnico(s) agent`} />
            </div>
          </div>
          <div className="grid gap-0 sm:grid-cols-2">
            <UserTile icon={MonitorCog} label="Acesso painel" value={summary.panelUsers} detail={`${summary.admins} admin, ${summary.managers} gestor(es)`} tone={summary.panelUsers ? "info" : "muted"} />
            <UserTile icon={UserCog} label="Tecnicos agent" value={summary.agents} detail="Credenciais de captura e instalacao" tone={summary.agents ? "info" : "warn"} />
            <UserTile icon={AlertTriangle} label="Sem depto." value={summary.withoutDepartment} detail="Afeta relatorios por centro de custo" tone={summary.withoutDepartment ? "warn" : "ok"} />
            <UserTile icon={ShieldCheck} label="Inativos" value={summary.inactive} detail="Mantidos para preservar historico" tone={summary.inactive ? "warn" : "ok"} />
          </div>
        </div>
      </Surface>

      {isAdmin ? (
        <Surface as="form" className="mb-4 grid gap-3 p-4 xl:grid-cols-[160px_minmax(180px,1fr)_150px_190px_150px_120px_auto]" onSubmit={submit}>
          <Input
            placeholder="Login"
            value={form.username}
            onChange={(event) => setForm({ ...form, username: event.target.value })}
            required
            disabled={editingId !== null}
          />
          <Input
            placeholder="Nome"
            value={form.full_name}
            onChange={(event) => setForm({ ...form, full_name: event.target.value })}
            required
          />
          <select
            className="h-9 rounded-md border bg-white px-3 text-sm outline-none transition-colors focus-visible:border-primary focus-visible:ring-2 focus-visible:ring-ring/20 disabled:bg-muted disabled:text-muted-foreground"
            value={editingAgent ? "agent" : form.role}
            onChange={(event) => setForm({ ...form, role: event.target.value })}
            disabled={editingAgent}
          >
            {editingAgent ? <option value="agent">Tecnico agent</option> : null}
            {humanRoleOptions.map((role) => (
              <option key={role.value} value={role.value}>
                {role.label}
              </option>
            ))}
          </select>
          {showPasswordField ? (
            <div className="flex flex-col gap-1">
              <Input
                placeholder={editingId ? "Nova senha" : "Senha"}
                type="password"
                value={form.password}
                onChange={(event) => setForm({ ...form, password: event.target.value })}
                minLength={8}
                autoComplete="new-password"
                required={creatingPanelUser}
                title={editingAgent ? "Troca a senha usada no instalador e no agent" : "Senha para acesso ao painel"}
              />
              <span className="text-[11px] text-muted-foreground">{editingId ? "Preencha para trocar" : "Obrigatoria para painel"}</span>
            </div>
          ) : null}
          <select
            className="h-9 rounded-md border bg-white px-3 text-sm outline-none transition-colors focus-visible:border-primary focus-visible:ring-2 focus-visible:ring-ring/20"
            value={form.department_id}
            onChange={(event) => setForm({ ...form, department_id: event.target.value })}
          >
            <option value="">Sem departamento</option>
            {departments.map((department) => (
              <option key={department.id} value={department.id}>
                {department.name}
              </option>
            ))}
          </select>
          <Input
            placeholder="Limite"
            type="number"
            value={form.monthly_limit}
            onChange={(event) => setForm({ ...form, monthly_limit: event.target.value })}
          />
          <div className="flex flex-wrap items-center gap-2">
            {showBalance ? (
              <Input
                className="w-32"
                placeholder="Saldo R$"
                type="number"
                step="0.01"
                value={form.monthly_balance}
                onChange={(event) => setForm({ ...form, monthly_balance: event.target.value })}
              />
            ) : null}
            {editingId ? (
              <label className="flex items-center gap-2 px-2 text-sm font-medium">
                <input
                  type="checkbox"
                  className="h-4 w-4 rounded border-gray-300 text-primary focus:ring-primary"
                  checked={form.is_active}
                  onChange={(event) => setForm({ ...form, is_active: event.target.checked })}
                />
                Ativo
              </label>
            ) : null}
            <Button type="submit">
              <Plus className="h-4 w-4" />
              {editingId ? "Salvar" : "Cadastrar"}
            </Button>
            {editingId ? (
              <Button type="button" variant="outline" onClick={resetForm}>
                Cancelar
              </Button>
            ) : null}
          </div>
        </Surface>
      ) : null}

      {error ? <Surface className="mb-4 border-red-200 bg-red-50 p-3 text-sm text-red-800">{error}</Surface> : null}

      <Surface className="mb-4 overflow-hidden">
        <div className="border-b bg-muted/30 p-4">
          <div className="flex items-center gap-2 text-sm font-semibold">
            <Building2 className="h-4 w-4 text-primary" />
            Departamentos
          </div>
        </div>
        <div className={`grid gap-4 p-4 ${isAdmin ? "lg:grid-cols-[360px_1fr]" : ""}`}>
          {isAdmin ? (
            <form className="flex flex-col gap-3" onSubmit={submitDepartment}>
              <Input
                placeholder="Nome do departamento"
                value={departmentForm.name}
                onChange={(event) => setDepartmentForm({ ...departmentForm, name: event.target.value })}
                required
              />
              <Input
                placeholder="Centro de custo"
                value={departmentForm.cost_center}
                onChange={(event) => setDepartmentForm({ ...departmentForm, cost_center: event.target.value })}
              />
              <div className="flex gap-2">
                <Button type="submit">
                  <Plus className="h-4 w-4" />
                  {editingDepartmentId ? "Salvar" : "Cadastrar"}
                </Button>
                {editingDepartmentId ? (
                  <Button type="button" variant="outline" onClick={resetDepartmentForm}>
                    Cancelar
                  </Button>
                ) : null}
              </div>
              {departmentError ? <div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-800">{departmentError}</div> : null}
            </form>
          ) : null}
          <div className="overflow-x-auto">
            {departments.length === 0 ? (
              <div className="rounded-md border border-dashed p-6 text-center text-sm text-muted-foreground">Nenhum departamento cadastrado.</div>
            ) : (
              <table className="w-full text-sm">
                <thead className="text-left text-xs uppercase tracking-wide text-muted-foreground">
                  <tr>
                    <th className="p-2">Departamento</th>
                    <th className="p-2">Centro de custo</th>
                    {isAdmin ? <th className="p-2 text-right">Acoes</th> : null}
                  </tr>
                </thead>
                <tbody>
                  {departments.map((department) => (
                    <tr key={department.id} className="border-t">
                      <td className="p-2 font-medium">{department.name}</td>
                      <td className="p-2 text-muted-foreground">{department.cost_center ?? "-"}</td>
                      {isAdmin ? (
                        <td className="p-2 text-right">
                          <div className="flex justify-end gap-1">
                            <Button variant="ghost" onClick={() => startEditDepartment(department)} title="Editar departamento" className="h-8 w-8 p-0">
                              <Edit className="h-4 w-4 text-muted-foreground hover:text-foreground" />
                            </Button>
                            <Button variant="ghost" onClick={() => deleteDepartment(department)} title="Excluir departamento" className="h-8 w-8 p-0">
                              <Trash2 className="h-4 w-4 text-red-600 hover:text-red-700" />
                            </Button>
                          </div>
                        </td>
                      ) : null}
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      </Surface>

      <Surface className="overflow-hidden">
        <div className="border-b bg-muted/30 p-4 text-sm font-semibold">
          Lista de usuarios <span className="text-muted-foreground">({users.length})</span>
        </div>
        {users.length === 0 ? (
          <div className="p-8 text-center text-sm text-muted-foreground">Nenhum usuario cadastrado.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-muted/80 text-left text-xs uppercase tracking-wide text-muted-foreground">
                <tr>
                  <th className="p-4">Usuario</th>
                  <th className="p-4">Nome</th>
                  <th className="p-4">Departamento</th>
                  <th className="p-4 text-right">Limite</th>
                  {showBalance ? <th className="p-4 text-right">Saldo</th> : null}
                  {showBalance ? <th className="p-4 text-right">Gasto</th> : null}
                  <th className="p-4">Perfil</th>
                  <th className="p-4">Status</th>
                  {isAdmin ? <th className="p-4 text-right">Acoes</th> : null}
                </tr>
              </thead>
              <tbody>
                {users.map((user) => {
                  const canDelete = user.username !== "admin" && user.username !== "agent";
                  return (
                    <tr key={user.id} className="border-t bg-white transition-colors hover:bg-muted/30">
                      <td className="whitespace-nowrap p-4 font-semibold">{user.username}</td>
                      <td className="min-w-[180px] p-4">{user.full_name}</td>
                      <td className="p-4 text-muted-foreground">{user.department_name ?? "-"}</td>
                      <td className="whitespace-nowrap p-4 text-right font-medium">
                        {user.monthly_limit !== null ? `${user.monthly_limit.toLocaleString("pt-BR")} pag.` : "-"}
                      </td>
                      {showBalance ? (
                        <td className="whitespace-nowrap p-4 text-right font-medium">
                          {user.monthly_balance !== null ? money(user.monthly_balance) : "-"}
                        </td>
                      ) : null}
                      {showBalance ? (
                        <td className="whitespace-nowrap p-4 text-right text-muted-foreground">
                          {user.used_balance !== null ? money(user.used_balance) : money(0)}
                        </td>
                      ) : null}
                      <td className="p-4">
                        <span className={`inline-flex rounded-full border px-2 py-0.5 text-xs font-semibold ${roleBadgeClass(user.role)}`}>
                          {roleLabel(user.role)}
                        </span>
                      </td>
                      <td className="p-4">
                        <span className={`inline-flex rounded-full border px-2 py-0.5 text-xs font-semibold ${user.is_active ? "border-green-200 bg-green-50 text-green-700" : "border-red-200 bg-red-50 text-red-700"}`}>
                          {user.is_active ? "Ativo" : "Inativo"}
                        </span>
                      </td>
                      {isAdmin ? (
                        <td className="p-4 text-right">
                          <div className="flex items-center justify-end gap-1">
                            <Button variant="ghost" onClick={() => startEdit(user)} title="Editar" className="h-8 w-8 p-0">
                              <Edit className="h-4 w-4 text-muted-foreground hover:text-foreground" />
                            </Button>
                            {canDelete ? (
                              <Button variant="ghost" onClick={() => deleteUser(user)} title="Excluir" className="h-8 w-8 p-0">
                                <Trash2 className="h-4 w-4 text-red-600 hover:text-red-700" />
                              </Button>
                            ) : null}
                          </div>
                        </td>
                      ) : null}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Surface>
    </ProtectedPage>
  );
}

function UserSignal({
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

function UserTile({
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
  tone: "ok" | "warn" | "info" | "muted";
}) {
  const toneClass =
    tone === "ok"
      ? "border-emerald-200 bg-emerald-50 text-emerald-700"
      : tone === "warn"
      ? "border-amber-200 bg-amber-50 text-amber-700"
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

function roleLabel(role: string) {
  const labels: Record<string, string> = {
    admin: "Administrador",
    manager: "Gestor",
    user: "Usuario",
    agent: "Tecnico agent",
  };
  return labels[role] ?? role;
}

function roleBadgeClass(role: string) {
  const classes: Record<string, string> = {
    admin: "border-blue-200 bg-blue-50 text-blue-700",
    manager: "border-cyan-200 bg-cyan-50 text-cyan-700",
    user: "border-slate-200 bg-slate-50 text-slate-700",
    agent: "border-amber-200 bg-amber-50 text-amber-700",
  };
  return classes[role] ?? "border-slate-200 bg-slate-50 text-slate-700";
}

function money(value: number) {
  return value.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}
