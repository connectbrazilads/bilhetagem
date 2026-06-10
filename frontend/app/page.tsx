"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Building2, Lock, LogIn, User } from "lucide-react";

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
      localStorage.setItem("token", data.access_token);
      localStorage.setItem("organization_slug", normalizedOrganization);
      router.push("/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha no login");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-background p-4">
      <Surface className="w-full max-w-sm p-5">
        <div className="mb-5">
          <h1 className="text-xl font-semibold">PrintBilling</h1>
          <p className="mt-1 text-sm text-muted-foreground">Acesse o painel administrativo.</p>
        </div>
        <form className="space-y-3" onSubmit={submit}>
          <label className="block text-sm font-medium">
            Empresa
            <div className="mt-1 flex items-center gap-2">
              <Building2 className="h-4 w-4 text-muted-foreground" />
              <Input
                value={organizationSlug}
                onChange={(event) => setOrganizationSlug(event.target.value.toLowerCase().replace(/\s+/g, "-"))}
                autoComplete="organization"
                required
              />
            </div>
          </label>
          <label className="block text-sm font-medium">
            Usuario
            <div className="mt-1 flex items-center gap-2">
              <User className="h-4 w-4 text-muted-foreground" />
              <Input value={username} onChange={(event) => setUsername(event.target.value)} autoComplete="username" required />
            </div>
          </label>
          <label className="block text-sm font-medium">
            Senha
            <div className="mt-1 flex items-center gap-2">
              <Lock className="h-4 w-4 text-muted-foreground" />
              <Input type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" required />
            </div>
          </label>
          {error ? <p className="text-sm text-destructive">{error}</p> : null}
          <Button className="w-full" disabled={loading}>
            <LogIn className="h-4 w-4" />
            {loading ? "Entrando..." : "Entrar"}
          </Button>
        </form>
      </Surface>
    </main>
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
