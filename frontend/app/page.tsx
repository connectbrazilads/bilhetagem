"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { Lock, LogIn, User } from "lucide-react";

import { Button, Input, Surface } from "@/components/ui";
import { API_URL } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`${API_URL}/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password })
      });
      if (!response.ok) {
        throw new Error("Credenciais invalidas");
      }
      const data = await response.json();
      localStorage.setItem("token", data.access_token);
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
            Usuario
            <div className="mt-1 flex items-center gap-2">
              <User className="h-4 w-4 text-muted-foreground" />
              <Input value={username} onChange={(event) => setUsername(event.target.value)} />
            </div>
          </label>
          <label className="block text-sm font-medium">
            Senha
            <div className="mt-1 flex items-center gap-2">
              <Lock className="h-4 w-4 text-muted-foreground" />
              <Input type="password" value={password} onChange={(event) => setPassword(event.target.value)} />
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
