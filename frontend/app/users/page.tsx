"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { Edit, Plus, ShieldCheck, Trash2, Users } from "lucide-react";

import { ProtectedPage } from "@/components/protected-page";
import { Button, Input, Surface } from "@/components/ui";
import { apiFetch } from "@/lib/api";

type UserRow = {
  id: number;
  username: string;
  full_name: string;
  role: string;
  department_name: string | null;
  is_active: boolean;
  monthly_limit: number | null;
  monthly_balance: number | null;
  used_balance: number | null;
};

const emptyForm = {
  username: "",
  full_name: "",
  department_name: "",
  monthly_limit: "500",
  monthly_balance: "50.00",
  is_active: true,
};

export default function UsersPage() {
  const [users, setUsers] = useState<UserRow[]>([]);
  const [form, setForm] = useState(emptyForm);
  const [error, setError] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [showBalance, setShowBalance] = useState(true);

  async function load() {
    const token = localStorage.getItem("token");
    if (!token) return;
    await apiFetch<UserRow[]>("/users", token).then(setUsers).catch(() => setUsers([]));

    try {
      const settingsData = await apiFetch<{ show_balance: boolean }>("/settings", token);
      setShowBalance(settingsData.show_balance);
    } catch {
      setShowBalance(true);
    }
  }

  useEffect(() => {
    load();
  }, []);

  const summary = useMemo(() => {
    return {
      total: users.length,
      active: users.filter((user) => user.is_active).length,
      admins: users.filter((user) => user.role === "admin").length,
    };
  }, [users]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    const token = localStorage.getItem("token");
    if (!token) return;
    setError(null);
    try {
      if (editingId) {
        await apiFetch<UserRow>(`/users/${editingId}`, token, {
          method: "PUT",
          body: JSON.stringify({
            full_name: form.full_name,
            department_name: form.department_name || null,
            monthly_limit: Number(form.monthly_limit),
            monthly_balance: Number(form.monthly_balance),
            role: "user",
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
            department_name: form.department_name || null,
            monthly_limit: Number(form.monthly_limit),
            monthly_balance: Number(form.monthly_balance),
            role: "user",
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
    setEditingId(user.id);
    setForm({
      username: user.username,
      full_name: user.full_name,
      department_name: user.department_name ?? "",
      monthly_limit: String(user.monthly_limit ?? 500),
      monthly_balance: String(user.monthly_balance ?? 50.0),
      is_active: user.is_active,
    });
  }

  function resetForm() {
    setEditingId(null);
    setForm(emptyForm);
  }

  async function deleteUser(user: UserRow) {
    if (user.username === "admin" || user.username === "agent") {
      setError("Usuarios tecnicos nao podem ser excluidos.");
      return;
    }
    const confirmed = window.confirm(`Excluir o usuario "${user.full_name || user.username}" e os historicos vinculados a ele?`);
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
          <p className="mt-1 text-sm text-muted-foreground">Cadastre usuarios, departamentos e limites de impressao.</p>
        </div>
      </div>

      <div className="mb-4 grid gap-4 md:grid-cols-3">
        <SummaryCard label="Usuarios cadastrados" value={summary.total} icon={Users} />
        <SummaryCard label="Usuarios ativos" value={summary.active} icon={ShieldCheck} />
        <SummaryCard label="Administradores" value={summary.admins} icon={ShieldCheck} />
      </div>

      <Surface as="form" className="mb-4 grid gap-3 p-4 lg:grid-cols-[180px_1fr_190px_130px_auto]" onSubmit={submit}>
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
        <Input
          placeholder="Departamento"
          value={form.department_name}
          onChange={(event) => setForm({ ...form, department_name: event.target.value })}
        />
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

      {error ? <Surface className="mb-4 border-red-200 bg-red-50 p-3 text-sm text-red-800">{error}</Surface> : null}

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
                  <th className="p-4 text-right">Acoes</th>
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
                          {user.monthly_balance !== null ? `R$ ${user.monthly_balance.toFixed(2)}` : "-"}
                        </td>
                      ) : null}
                      {showBalance ? (
                        <td className="whitespace-nowrap p-4 text-right text-muted-foreground">
                          {user.used_balance !== null ? `R$ ${user.used_balance.toFixed(2)}` : "R$ 0.00"}
                        </td>
                      ) : null}
                      <td className="p-4">{user.role}</td>
                      <td className="p-4">
                        <span className={`inline-flex rounded-full border px-2 py-0.5 text-xs font-semibold ${user.is_active ? "border-green-200 bg-green-50 text-green-700" : "border-red-200 bg-red-50 text-red-700"}`}>
                          {user.is_active ? "Ativo" : "Inativo"}
                        </span>
                      </td>
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
