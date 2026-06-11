"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Activity, Building2, Lock, LogIn, MonitorCog, Printer, ShieldCheck, User } from "lucide-react";

import { Button, Input, Surface } from "@/components/ui";
import { API_URL } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  const [organizationSlug, setOrganizationSlug] = useState("default");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const savedOrganization = localStorage.getItem("organization_slug");
    if (savedOrganization) setOrganizationSlug(savedOrganization);
  }, []);

  async function submit(event: FormEvent) {
    event.preventDefault();
    const normalizedOrganization = organizationSlug.trim().toLowerCase();
    if (!normalizedOrganization) {
      setError("Informe a empresa para acessar.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`${API_URL}/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: username.trim(), password, organization_slug: normalizedOrganization })
      });
      if (!response.ok) {
        throw new Error(await readLoginError(response));
      }
      const data = await response.json();
      if (data.role === "agent") {
        setError("Usuario tecnico do agent nao acessa o painel administrativo.");
        return;
      }
      localStorage.setItem("token", data.access_token);
      localStorage.setItem("organization_slug", data.organization_slug || normalizedOrganization);
      if (data.organization_name) localStorage.setItem("organization_name", data.organization_name);
      if (data.organization_billing_status) localStorage.setItem("organization_billing_status", data.organization_billing_status);
      router.push("/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha no login");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="grid min-h-screen bg-background lg:grid-cols-[1fr_460px]">
      <section className="hidden bg-slate-950 p-8 text-white lg:flex lg:flex-col lg:justify-between">
        <div>
          <div className="flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-md bg-white text-sm font-bold text-slate-950">PB</div>
            <div>
              <div className="text-lg font-bold">PrintBilling</div>
              <div className="text-xs text-slate-400">Bilhetagem SaaS</div>
            </div>
          </div>
          <div className="mt-16 max-w-xl">
            <div className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/10 px-3 py-1 text-xs font-semibold text-slate-200">
              <ShieldCheck className="h-3.5 w-3.5" />
              Ambiente operacional
            </div>
            <h1 className="mt-5 text-4xl font-bold leading-tight">Bilhetagem de impressao em operacao.</h1>
            <p className="mt-4 max-w-lg text-sm leading-6 text-slate-300">Ambiente administrativo para contratos, agents e relatorios.</p>
          </div>
        </div>
        <div className="grid grid-cols-3 gap-3">
          <LoginSignal icon={MonitorCog} label="Agents" value="online" />
          <LoginSignal icon={Printer} label="SNMP" value="ativo" />
          <LoginSignal icon={Activity} label="Piloto" value="pronto" />
        </div>
      </section>

      <section className="flex min-h-screen items-center justify-center p-4 sm:p-8">
        <Surface className="w-full max-w-md p-6 sm:p-7">
          <div className="mb-6">
            <div className="mb-4 flex h-11 w-11 items-center justify-center rounded-md bg-slate-950 text-sm font-bold text-white lg:hidden">PB</div>
            <h2 className="text-2xl font-bold">Acessar painel</h2>
            <p className="mt-1 text-sm text-muted-foreground">Entre com empresa, usuario e senha.</p>
          </div>
        <form className="space-y-4" onSubmit={submit}>
          <label className="block text-sm font-medium">
            Empresa
            <div className="mt-1.5 flex items-center gap-2 rounded-md border bg-white px-3 focus-within:border-primary focus-within:ring-2 focus-within:ring-ring/20">
              <Building2 className="h-4 w-4 shrink-0 text-muted-foreground" />
              <Input
                className="border-0 bg-transparent px-0 shadow-none focus-visible:border-0 focus-visible:bg-transparent focus-visible:ring-0"
                value={organizationSlug}
                onChange={(event) => setOrganizationSlug(event.target.value.toLowerCase().replace(/\s+/g, "-"))}
                autoComplete="organization"
                required
              />
            </div>
          </label>
          <label className="block text-sm font-medium">
            Usuario
            <div className="mt-1.5 flex items-center gap-2 rounded-md border bg-white px-3 focus-within:border-primary focus-within:ring-2 focus-within:ring-ring/20">
              <User className="h-4 w-4 shrink-0 text-muted-foreground" />
              <Input
                className="border-0 bg-transparent px-0 shadow-none focus-visible:border-0 focus-visible:bg-transparent focus-visible:ring-0"
                value={username}
                onChange={(event) => setUsername(event.target.value)}
                autoComplete="username"
                required
              />
            </div>
          </label>
          <label className="block text-sm font-medium">
            Senha
            <div className="mt-1.5 flex items-center gap-2 rounded-md border bg-white px-3 focus-within:border-primary focus-within:ring-2 focus-within:ring-ring/20">
              <Lock className="h-4 w-4 shrink-0 text-muted-foreground" />
              <Input
                className="border-0 bg-transparent px-0 shadow-none focus-visible:border-0 focus-visible:bg-transparent focus-visible:ring-0"
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                autoComplete="current-password"
                required
              />
            </div>
          </label>
          {error ? <div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm font-semibold text-red-700">{error}</div> : null}
          <Button className="h-10 w-full" disabled={loading}>
            <LogIn className="h-4 w-4" />
            {loading ? "Entrando..." : "Entrar"}
          </Button>
        </form>
        </Surface>
      </section>
    </main>
  );
}

function LoginSignal({ icon: Icon, label, value }: { icon: typeof MonitorCog; label: string; value: string }) {
  return (
    <div className="rounded-lg border border-white/10 bg-white/10 p-4">
      <Icon className="h-4 w-4 text-cyan-300" />
      <div className="mt-3 text-xs text-slate-400">{label}</div>
      <div className="text-sm font-bold">{value}</div>
    </div>
  );
}

async function readLoginError(response: Response) {
  const fallback = "Credenciais invalidas";
  const text = await response.text();
  if (!text) return fallback;
  try {
    const parsed = JSON.parse(text);
    if (typeof parsed.detail === "string") return parsed.detail;
    if (Array.isArray(parsed.detail)) return "Revise os dados de login informados.";
  } catch {}
  return text || fallback;
}
