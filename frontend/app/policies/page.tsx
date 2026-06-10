"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { Edit, Plus, ShieldCheck, TestTube2, Trash2 } from "lucide-react";

import { ProtectedPage } from "@/components/protected-page";
import { Button, Input, Surface } from "@/components/ui";
import { apiFetch } from "@/lib/api";

type PolicyRuleType = "always" | "max_pages" | "color" | "time_window";
type PolicyAction = "allow" | "block" | "require_release" | "force_mono";

type PolicyRow = {
  id: number;
  name: string;
  description: string | null;
  priority: number;
  is_active: boolean;
  rule_type: PolicyRuleType;
  action: PolicyAction;
  user_id: number | null;
  department_id: number | null;
  printer_id: number | null;
  printer_alias_id: number | null;
  queue_name: string | null;
  max_pages: number | null;
  days_of_week: string | null;
  start_time: string | null;
  end_time: string | null;
  message: string | null;
  created_at: string;
};

type UserRow = {
  id: number;
  username: string;
  full_name: string;
  department_id: number | null;
  department_name: string | null;
};

type DepartmentRow = {
  id: number;
  name: string;
};

type PrinterRow = {
  id: number;
  name: string;
  aliases?: {
    id: number;
    queue_name: string;
    computer_name: string | null;
    printer_id: number | null;
  }[];
};

type PolicySimulation = {
  matched: boolean;
  policy_id: number | null;
  policy_name: string | null;
  action: PolicyAction | null;
  reason: string | null;
  force_mono: boolean;
  effective_is_color: boolean;
  user_id: number;
  printer_id: number;
  printer_alias_id: number | null;
};

const emptyForm = {
  name: "",
  description: "",
  priority: "100",
  is_active: true,
  rule_type: "color" as PolicyRuleType,
  action: "block" as PolicyAction,
  user_id: "",
  department_id: "",
  printer_id: "",
  printer_alias_id: "",
  queue_name: "",
  max_pages: "",
  days_of_week: "",
  start_time: "",
  end_time: "",
  message: "",
};

const emptySimulationForm = {
  username: "",
  printer_name: "",
  pages: "1",
  is_color: false,
  queue_name: "",
};

const ruleLabels: Record<PolicyRuleType, string> = {
  always: "Sempre",
  max_pages: "Acima de paginas",
  color: "Colorido",
  time_window: "Horario",
};

const actionLabels: Record<PolicyAction, string> = {
  allow: "Permitir excecao",
  block: "Bloquear",
  require_release: "Exigir liberacao",
  force_mono: "Cobrar como P&B",
};

export default function PoliciesPage() {
  const [policies, setPolicies] = useState<PolicyRow[]>([]);
  const [users, setUsers] = useState<UserRow[]>([]);
  const [departments, setDepartments] = useState<DepartmentRow[]>([]);
  const [printers, setPrinters] = useState<PrinterRow[]>([]);
  const [form, setForm] = useState(emptyForm);
  const [simulationForm, setSimulationForm] = useState(emptySimulationForm);
  const [simulation, setSimulation] = useState<PolicySimulation | null>(null);
  const [simulationError, setSimulationError] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    const token = localStorage.getItem("token");
    if (!token) return;
    await Promise.all([
      apiFetch<PolicyRow[]>("/policies", token).then(setPolicies).catch(() => setPolicies([])),
      apiFetch<UserRow[]>("/users", token).then(setUsers).catch(() => setUsers([])),
      apiFetch<DepartmentRow[]>("/departments", token).then(setDepartments).catch(() => setDepartments([])),
      apiFetch<PrinterRow[]>("/printers", token).then(setPrinters).catch(() => setPrinters([])),
    ]);
  }

  useEffect(() => {
    load();
  }, []);

  useEffect(() => {
    setSimulationForm((current) => ({
      ...current,
      username: current.username || users[0]?.username || "",
      printer_name: current.printer_name || printers[0]?.name || "",
    }));
  }, [users, printers]);

  const summary = useMemo(() => {
    return {
      total: policies.length,
      active: policies.filter((policy) => policy.is_active).length,
      blockers: policies.filter((policy) => policy.action === "block").length,
    };
  }, [policies]);

  const aliases = useMemo(() => {
    return printers.flatMap((printer) =>
      (printer.aliases ?? []).map((alias) => ({
        ...alias,
        printer_name: printer.name,
      })),
    );
  }, [printers]);

  const selectedUser = users.find((user) => user.id.toString() === form.user_id);
  const selectedDepartment = departments.find((department) => department.id.toString() === form.department_id);
  const selectedPrinter = printers.find((printer) => printer.id.toString() === form.printer_id);
  const selectedAlias = aliases.find((alias) => alias.id.toString() === form.printer_alias_id);

  function payload() {
    return {
      name: form.name,
      description: form.description || null,
      priority: Number(form.priority),
      is_active: form.is_active,
      rule_type: form.rule_type,
      action: form.action,
      user_id: form.user_id ? Number(form.user_id) : null,
      department_id: form.department_id ? Number(form.department_id) : null,
      printer_id: form.printer_id ? Number(form.printer_id) : null,
      printer_alias_id: form.printer_alias_id ? Number(form.printer_alias_id) : null,
      queue_name: form.queue_name || null,
      max_pages: form.max_pages ? Number(form.max_pages) : null,
      days_of_week: form.days_of_week || null,
      start_time: form.start_time || null,
      end_time: form.end_time || null,
      message: form.message || null,
    };
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    const token = localStorage.getItem("token");
    if (!token) return;
    setError(null);
    try {
      if (editingId) {
        await apiFetch<PolicyRow>(`/policies/${editingId}`, token, {
          method: "PUT",
          body: JSON.stringify(payload()),
        });
      } else {
        await apiFetch<PolicyRow>("/policies", token, {
          method: "POST",
          body: JSON.stringify(payload()),
        });
      }
      setForm(emptyForm);
      setEditingId(null);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao salvar politica");
    }
  }

  function startEdit(policy: PolicyRow) {
    setEditingId(policy.id);
    setForm({
      name: policy.name,
      description: policy.description ?? "",
      priority: String(policy.priority),
      is_active: policy.is_active,
      rule_type: policy.rule_type,
      action: policy.action,
      user_id: policy.user_id?.toString() ?? "",
      department_id: policy.department_id?.toString() ?? "",
      printer_id: policy.printer_id?.toString() ?? "",
      printer_alias_id: policy.printer_alias_id?.toString() ?? "",
      queue_name: policy.queue_name ?? "",
      max_pages: policy.max_pages?.toString() ?? "",
      days_of_week: policy.days_of_week ?? "",
      start_time: policy.start_time?.slice(0, 5) ?? "",
      end_time: policy.end_time?.slice(0, 5) ?? "",
      message: policy.message ?? "",
    });
  }

  async function deletePolicy(policy: PolicyRow) {
    if (!window.confirm(`Excluir a politica "${policy.name}"?`)) return;
    const token = localStorage.getItem("token");
    if (!token) return;
    setError(null);
    try {
      await apiFetch<{ status: string }>(`/policies/${policy.id}`, token, { method: "DELETE" });
      if (editingId === policy.id) {
        setEditingId(null);
        setForm(emptyForm);
      }
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao excluir politica");
    }
  }

  async function simulatePolicy(event: FormEvent) {
    event.preventDefault();
    const token = localStorage.getItem("token");
    if (!token) return;
    setSimulation(null);
    setSimulationError(null);
    try {
      const result = await apiFetch<PolicySimulation>("/policies/simulate", token, {
        method: "POST",
        body: JSON.stringify({
          username: simulationForm.username,
          printer_name: simulationForm.printer_name,
          pages: Number(simulationForm.pages),
          is_color: simulationForm.is_color,
          queue_name: simulationForm.queue_name || null,
        }),
      });
      setSimulation(result);
    } catch (err) {
      setSimulationError(err instanceof Error ? err.message : "Falha ao simular politica");
    }
  }

  function describePolicy(policy: PolicyRow) {
    const parts = [ruleLabels[policy.rule_type]];
    if (policy.max_pages) parts.push(`>${policy.max_pages} pag.`);
    if (policy.start_time && policy.end_time) parts.push(`${policy.start_time.slice(0, 5)}-${policy.end_time.slice(0, 5)}`);
    if (policy.queue_name) parts.push(`Fila ${policy.queue_name}`);
    if (policy.user_id) {
      const user = users.find((item) => item.id === policy.user_id);
      parts.push(user ? `Usuario ${user.username}` : `Usuario #${policy.user_id}`);
    }
    if (policy.department_id) {
      const department = departments.find((item) => item.id === policy.department_id);
      parts.push(department ? `Depto ${department.name}` : `Depto #${policy.department_id}`);
    }
    if (policy.printer_id) {
      const printer = printers.find((item) => item.id === policy.printer_id);
      parts.push(printer ? `Impressora ${printer.name}` : `Impressora #${policy.printer_id}`);
    }
    if (policy.printer_alias_id) {
      const alias = aliases.find((item) => item.id === policy.printer_alias_id);
      parts.push(alias ? `Fila ${alias.queue_name}` : `Alias #${policy.printer_alias_id}`);
    }
    return parts.join(" - ");
  }

  function changeRuleType(ruleType: PolicyRuleType) {
    setForm({
      ...form,
      rule_type: ruleType,
      max_pages: ruleType === "max_pages" ? form.max_pages : "",
      start_time: ruleType === "time_window" ? form.start_time : "",
      end_time: ruleType === "time_window" ? form.end_time : "",
    });
  }

  return (
    <ProtectedPage>
      <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Politicas</h1>
          <p className="mt-1 text-sm text-muted-foreground">Defina regras de bloqueio, liberacao e excecoes por usuario, departamento, impressora ou fila.</p>
        </div>
      </div>

      <div className="mb-4 grid gap-4 md:grid-cols-3">
        <Summary label="Politicas" value={summary.total} />
        <Summary label="Ativas" value={summary.active} />
        <Summary label="Bloqueios" value={summary.blockers} />
      </div>

      <Surface as="form" className="mb-4 grid gap-3 p-4" onSubmit={submit}>
        <div className="grid gap-3 lg:grid-cols-[1fr_120px_170px_170px_130px]">
          <Input placeholder="Nome da politica" value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} required />
          <Input placeholder="Prioridade" type="number" value={form.priority} onChange={(event) => setForm({ ...form, priority: event.target.value })} required />
          <select className="h-9 rounded-md border bg-white px-3 text-sm" value={form.rule_type} onChange={(event) => changeRuleType(event.target.value as PolicyRuleType)}>
            {Object.entries(ruleLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
          <select className="h-9 rounded-md border bg-white px-3 text-sm" value={form.action} onChange={(event) => setForm({ ...form, action: event.target.value as PolicyAction })}>
            {Object.entries(actionLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
          <label className="flex items-center gap-2 px-2 text-sm font-medium">
            <input type="checkbox" className="h-4 w-4" checked={form.is_active} onChange={(event) => setForm({ ...form, is_active: event.target.checked })} />
            Ativa
          </label>
        </div>

        <div className="grid gap-3 lg:grid-cols-5">
          <Input
            placeholder="Max paginas"
            type="number"
            value={form.max_pages}
            onChange={(event) => setForm({ ...form, max_pages: event.target.value })}
            disabled={form.rule_type !== "max_pages"}
            required={form.rule_type === "max_pages"}
          />
          <Input placeholder="Dias: 0,1,2 ou seg,ter" value={form.days_of_week} onChange={(event) => setForm({ ...form, days_of_week: event.target.value })} />
          <Input type="time" value={form.start_time} onChange={(event) => setForm({ ...form, start_time: event.target.value })} disabled={form.rule_type !== "time_window"} required={form.rule_type === "time_window"} />
          <Input type="time" value={form.end_time} onChange={(event) => setForm({ ...form, end_time: event.target.value })} disabled={form.rule_type !== "time_window"} required={form.rule_type === "time_window"} />
          <Input placeholder="Mensagem" value={form.message} onChange={(event) => setForm({ ...form, message: event.target.value })} />
        </div>

        <div className="grid gap-3 lg:grid-cols-[1fr_1fr_1fr_1fr_1fr_auto]">
          <select className="h-9 rounded-md border bg-white px-3 text-sm" value={form.user_id} onChange={(event) => setForm({ ...form, user_id: event.target.value })}>
            <option value="">Todos os usuarios</option>
            {users.map((user) => <option key={user.id} value={user.id}>{user.username} - {user.full_name}</option>)}
          </select>
          <select className="h-9 rounded-md border bg-white px-3 text-sm" value={form.department_id} onChange={(event) => setForm({ ...form, department_id: event.target.value })}>
            <option value="">Todos departamentos</option>
            {departments.map((department) => (
              <option key={department.id} value={department.id}>
                {department.name}
              </option>
            ))}
          </select>
          <select className="h-9 rounded-md border bg-white px-3 text-sm" value={form.printer_id} onChange={(event) => setForm({ ...form, printer_id: event.target.value })}>
            <option value="">Todas impressoras</option>
            {printers.map((printer) => <option key={printer.id} value={printer.id}>{printer.name}</option>)}
          </select>
          <select className="h-9 rounded-md border bg-white px-3 text-sm" value={form.printer_alias_id} onChange={(event) => setForm({ ...form, printer_alias_id: event.target.value })}>
            <option value="">Todas filas detectadas</option>
            {aliases.map((alias) => (
              <option key={alias.id} value={alias.id}>
                {alias.queue_name} - {alias.computer_name || alias.printer_name}
              </option>
            ))}
          </select>
          <Input placeholder="Nome da fila" value={form.queue_name} onChange={(event) => setForm({ ...form, queue_name: event.target.value })} />
          <div className="flex gap-2">
            <Button type="submit">
              <Plus className="h-4 w-4" />
              {editingId ? "Salvar" : "Criar"}
            </Button>
            {editingId ? (
              <Button type="button" variant="outline" onClick={() => { setEditingId(null); setForm(emptyForm); }}>
                Cancelar
              </Button>
            ) : null}
          </div>
        </div>
        <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
          {selectedUser ? <span className="rounded-full bg-muted px-2 py-1">Usuario: {selectedUser.username}</span> : null}
          {selectedDepartment ? <span className="rounded-full bg-muted px-2 py-1">Departamento: {selectedDepartment.name}</span> : null}
          {selectedPrinter ? <span className="rounded-full bg-muted px-2 py-1">Impressora: {selectedPrinter.name}</span> : null}
          {selectedAlias ? <span className="rounded-full bg-muted px-2 py-1">Fila: {selectedAlias.queue_name}</span> : null}
          {form.action === "force_mono" ? (
            <span className="rounded-full bg-amber-50 px-2 py-1 text-amber-700">
              Contabiliza como P&B; conversao fisica depende do driver/fila.
            </span>
          ) : null}
        </div>
      </Surface>

      {error ? <Surface className="mb-4 border-red-200 bg-red-50 p-3 text-sm text-red-800">{error}</Surface> : null}

      <Surface as="form" className="mb-4 grid gap-4 p-4" onSubmit={simulatePolicy}>
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-md bg-primary/10 text-primary">
            <TestTube2 className="h-4 w-4" />
          </div>
          <div>
            <h2 className="text-base font-semibold">Simular politica</h2>
            <p className="text-xs text-muted-foreground">Teste um trabalho hipotetico sem criar impressao nem consumir cota.</p>
          </div>
        </div>

        <div className="grid gap-3 lg:grid-cols-[1fr_1fr_110px_120px_1fr_auto]">
          <select
            className="h-9 rounded-md border bg-white px-3 text-sm"
            value={simulationForm.username}
            onChange={(event) => setSimulationForm({ ...simulationForm, username: event.target.value })}
            required
          >
            <option value="">Usuario</option>
            {users.map((user) => (
              <option key={user.id} value={user.username}>
                {user.username}
              </option>
            ))}
          </select>
          <select
            className="h-9 rounded-md border bg-white px-3 text-sm"
            value={simulationForm.printer_name}
            onChange={(event) => setSimulationForm({ ...simulationForm, printer_name: event.target.value })}
            required
          >
            <option value="">Impressora</option>
            {printers.map((printer) => (
              <option key={printer.id} value={printer.name}>
                {printer.name}
              </option>
            ))}
          </select>
          <Input
            type="number"
            min={1}
            placeholder="Paginas"
            value={simulationForm.pages}
            onChange={(event) => setSimulationForm({ ...simulationForm, pages: event.target.value })}
            required
          />
          <label className="flex items-center gap-2 px-2 text-sm font-medium">
            <input
              type="checkbox"
              className="h-4 w-4"
              checked={simulationForm.is_color}
              onChange={(event) => setSimulationForm({ ...simulationForm, is_color: event.target.checked })}
            />
            Colorido
          </label>
          <Input
            placeholder="Fila opcional"
            value={simulationForm.queue_name}
            onChange={(event) => setSimulationForm({ ...simulationForm, queue_name: event.target.value })}
          />
          <Button type="submit">
            <TestTube2 className="h-4 w-4" />
            Testar
          </Button>
        </div>

        {simulation ? (
          <div
            className={`rounded-md border p-3 text-sm ${
              simulation.matched ? "border-blue-200 bg-blue-50 text-blue-900" : "border-slate-200 bg-slate-50 text-slate-700"
            }`}
          >
            {simulation.matched ? (
              <span>
                Politica aplicada: <strong>{simulation.policy_name}</strong> ({simulation.action ? actionLabels[simulation.action] : "-"})
                {simulation.force_mono ? " - cobraria como P&B, sem alterar o driver" : ""}. {simulation.reason || ""}
              </span>
            ) : (
              <span>Nenhuma politica ativa seria aplicada para este trabalho.</span>
            )}
          </div>
        ) : null}
        {simulationError ? <div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-800">{simulationError}</div> : null}
      </Surface>

      <Surface className="overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-muted/80 text-left text-xs uppercase tracking-wide text-muted-foreground">
            <tr>
              <th className="p-4">Prioridade</th>
              <th className="p-4">Politica</th>
              <th className="p-4">Regra</th>
              <th className="p-4">Acao</th>
              <th className="p-4">Status</th>
              <th className="p-4 text-right">Acoes</th>
            </tr>
          </thead>
          <tbody>
            {policies.map((policy) => (
              <tr key={policy.id} className="border-t bg-white hover:bg-muted/30">
                <td className="p-4 font-semibold">{policy.priority}</td>
                <td className="p-4">
                  <div className="font-semibold">{policy.name}</div>
                  <div className="text-xs text-muted-foreground">{policy.description || policy.message || "-"}</div>
                </td>
                <td className="p-4 text-muted-foreground">{describePolicy(policy)}</td>
                <td className="p-4 font-medium">{actionLabels[policy.action]}</td>
                <td className="p-4">
                  <span className={`inline-flex rounded-full border px-2 py-0.5 text-xs font-semibold ${policy.is_active ? "border-green-200 bg-green-50 text-green-700" : "border-slate-200 bg-slate-50 text-slate-600"}`}>
                    {policy.is_active ? "Ativa" : "Inativa"}
                  </span>
                </td>
                <td className="p-4 text-right">
                  <div className="flex justify-end gap-1">
                    <Button variant="ghost" className="h-8 w-8 p-0" title="Editar" onClick={() => startEdit(policy)}>
                      <Edit className="h-4 w-4 text-muted-foreground" />
                    </Button>
                    <Button variant="ghost" className="h-8 w-8 p-0" title="Excluir" onClick={() => deletePolicy(policy)}>
                      <Trash2 className="h-4 w-4 text-red-600" />
                    </Button>
                  </div>
                </td>
              </tr>
            ))}
            {policies.length === 0 ? (
              <tr>
                <td className="p-8 text-center text-sm text-muted-foreground" colSpan={6}>
                  Nenhuma politica cadastrada.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </Surface>
    </ProtectedPage>
  );
}

function Summary({ label, value }: { label: string; value: number }) {
  return (
    <Surface className="p-5">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-muted-foreground">{label}</span>
        <div className="flex h-9 w-9 items-center justify-center rounded-md bg-primary/10 text-primary">
          <ShieldCheck className="h-4 w-4" />
        </div>
      </div>
      <div className="mt-3 text-3xl font-semibold">{value.toLocaleString("pt-BR")}</div>
    </Surface>
  );
}
