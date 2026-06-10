"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { Building2, Edit, Plus, ShieldCheck, Trash2, Users } from "lucide-react";

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
    return {
      total: users.length,
      active: users.filter((user) => user.is_active).length,
      admins: users.filter((user) => user.role === "admin").length,
      departments: departments.length,
    };
  }, [users, departments]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!isAdmin) return;
    const token = localStorage.getItem("token");
    if (!token) return;
    setError(null);
    try {
      if (editingId) {
        await apiFetch<UserRow>(`/users/${editingId}`, token, {
          method: "PUT",
          body: JSON.stringify({
            full_name: form.full_name,
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
    if (user.username === "admin" || user.username === "agent" || user.role === "agent") {
      setError("Usuarios tecnicos nao podem ser excluidos.");
      return;
    }
    const confirmed = window.confirm(`Excluir o usuario "${user.full_name || user.username}"? Usuarios com historico devem ser desativados para preservar relatorios.`);
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

      <div className="mb-4 grid gap-4 md:grid-cols-4">
        <SummaryCard label="Usuarios cadastrados" value={summary.total} icon={Users} />
        <SummaryCard label="Usuarios ativos" value={summary.active} icon={ShieldCheck} />
        <SummaryCard label="Administradores" value={summary.admins} icon={ShieldCheck} />
        <SummaryCard label="Departamentos" value={summary.departments} icon={Building2} />
      </div>

      {isAdmin ? (
        <Surface as="form" className="mb-4 grid gap-3 p-4 xl:grid-cols-[160px_1fr_150px_190px_120px_auto]" onSubmit={submit}>
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
                  const canDelete = user.username !== "admin" && user.username !== "agent" && user.role !== "agent";
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
                          {user.monthly_balance !== null ? `R$ ${user.monthly_balance.toFixed(2)}` : "-"}
                        </td>
                      ) : null}
                      {showBalance ? (
                        <td className="whitespace-nowrap p-4 text-right text-muted-foreground">
                          {user.used_balance !== null ? `R$ ${user.used_balance.toFixed(2)}` : "R$ 0.00"}
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

function SummaryCard({ label, value, icon: Icon }: { label: string; value: number; icon: typeof Users }) {
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
