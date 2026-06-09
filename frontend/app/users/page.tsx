"use client";

import { FormEvent, useEffect, useState } from "react";
import { Edit, Plus } from "lucide-react";

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

export default function UsersPage() {
  const [users, setUsers] = useState<UserRow[]>([]);
  const [form, setForm] = useState({ username: "", full_name: "", department_name: "", monthly_limit: "500", monthly_balance: "50.00", is_active: true });
  const [error, setError] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<number | null>(null);

  async function load() {
    const token = localStorage.getItem("token");
    if (!token) return;
    await apiFetch<UserRow[]>("/users", token).then(setUsers).catch(() => setUsers([]));
  }

  useEffect(() => {
    load();
  }, []);

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
            is_active: form.is_active
          })
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
            role: "user"
          })
        });
      }
      setForm({ username: "", full_name: "", department_name: "", monthly_limit: "500", monthly_balance: "50.00", is_active: true });
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
      is_active: user.is_active
    });
  }

  return (
    <ProtectedPage>
      <div className="mb-5 flex items-center justify-between">
        <h1 className="text-xl font-semibold">Usuários</h1>
      </div>
      <Surface as="form" className="mb-4 flex flex-wrap gap-3 items-center p-4" onSubmit={submit}>
        <Input
          className="w-full sm:w-48"
          placeholder="Login"
          value={form.username}
          onChange={(event) => setForm({ ...form, username: event.target.value })}
          required
          disabled={editingId !== null}
        />
        <Input
          className="w-full sm:flex-1 min-w-[200px]"
          placeholder="Nome"
          value={form.full_name}
          onChange={(event) => setForm({ ...form, full_name: event.target.value })}
          required
        />
        <Input
          className="w-full sm:w-48"
          placeholder="Departamento"
          value={form.department_name}
          onChange={(event) => setForm({ ...form, department_name: event.target.value })}
        />
        <Input
          className="w-full sm:w-32"
          placeholder="Limite Páginas"
          type="number"
          value={form.monthly_limit}
          onChange={(event) => setForm({ ...form, monthly_limit: event.target.value })}
        />
        <Input
          className="w-full sm:w-32"
          placeholder="Saldo Limite (R$)"
          type="number"
          step="0.01"
          value={form.monthly_balance}
          onChange={(event) => setForm({ ...form, monthly_balance: event.target.value })}
        />
        {editingId ? (
          <label className="flex items-center gap-2 text-sm select-none px-2 cursor-pointer">
            <input
              type="checkbox"
              className="h-4 w-4"
              checked={form.is_active}
              onChange={(event) => setForm({ ...form, is_active: event.target.checked })}
            />
            Ativo
          </label>
        ) : null}
        <div className="flex gap-2">
          <Button type="submit">
            {editingId ? "Salvar" : "Cadastrar"}
          </Button>
          {editingId ? (
            <Button
              type="button"
              variant="outline"
              onClick={() => {
                setEditingId(null);
                setForm({ username: "", full_name: "", department_name: "", monthly_limit: "500", monthly_balance: "50.00", is_active: true });
              }}
            >
              Cancelar
            </Button>
          ) : null}
        </div>
      </Surface>
      {error ? <Surface className="mb-4 p-3 text-sm text-destructive">{error}</Surface> : null}
      <Surface className="overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-muted text-left">
            <tr>
              <th className="p-3">Usuário</th>
              <th className="p-3">Nome</th>
              <th className="p-3">Departamento</th>
              <th className="p-3">Limite Páginas</th>
              <th className="p-3">Saldo Mensal</th>
              <th className="p-3">Saldo Gasto</th>
              <th className="p-3">Perfil</th>
              <th className="p-3">Status</th>
              <th className="p-3 text-right">Ações</th>
            </tr>
          </thead>
          <tbody>
            {users.map((user) => {
              const remBalance = (user.monthly_balance ?? 0) - (user.used_balance ?? 0);
              return (
                <tr key={user.id} className="border-t animate-fade-in">
                  <td className="p-3 font-medium">{user.username}</td>
                  <td className="p-3">{user.full_name}</td>
                  <td className="p-3">{user.department_name ?? "-"}</td>
                  <td className="p-3">{user.monthly_limit !== null ? `${user.monthly_limit} pag.` : "-"}</td>
                  <td className="p-3">
                    {user.monthly_balance !== null ? `R$ ${user.monthly_balance.toFixed(2)}` : "-"}
                  </td>
                  <td className="p-3 text-muted-foreground">
                    {user.used_balance !== null ? `R$ ${user.used_balance.toFixed(2)}` : "R$ 0,00"}
                  </td>
                  <td className="p-3">{user.role}</td>
                  <td className="p-3">
                    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${user.is_active ? "bg-green-50 text-green-700 border border-green-200" : "bg-red-50 text-red-700 border border-red-200"}`}>
                      {user.is_active ? "Ativo" : "Inativo"}
                    </span>
                  </td>
                  <td className="p-3 text-right">
                    <Button variant="ghost" onClick={() => startEdit(user)} title="Editar">
                      <Edit className="h-4 w-4 text-muted-foreground hover:text-foreground" />
                    </Button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </Surface>
    </ProtectedPage>
  );
}
