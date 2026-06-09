"use client";

import { useState, useEffect } from "react";
import { Save, RefreshCw, CheckCircle, AlertCircle, Server } from "lucide-react";

import { ProtectedPage } from "@/components/protected-page";
import { Button, Input, Surface } from "@/components/ui";
import { apiFetch } from "@/lib/api";

export default function SettingsPage() {
  // General configurations
  const [defaultQuota, setDefaultQuota] = useState(500);
  const [apiUrl, setApiUrl] = useState("http://localhost:8000");
  const [autoCreateUsers, setAutoCreateUsers] = useState(true);
  const [blockingEnabled, setBlockingEnabled] = useState(true);
  const [showBalance, setShowBalance] = useState(true);
  const [safeReleaseEnabled, setSafeReleaseEnabled] = useState(true);

  // LDAP configurations
  const [ldapServer, setLdapServer] = useState("ldap://localhost:389");
  const [ldapBindDn, setLdapBindDn] = useState("cn=admin,dc=example,dc=com");
  const [ldapBindPassword, setLdapBindPassword] = useState("secret");
  const [ldapSearchBase, setLdapSearchBase] = useState("dc=example,dc=com");

  // Feedback states
  const [statusMsg, setStatusMsg] = useState<{ text: string; type: "success" | "error" } | null>(null);
  const [loading, setLoading] = useState(false);

  // Load from backend & localStorage
  useEffect(() => {
    const token = localStorage.getItem("token");
    if (token) {
      apiFetch<{
        default_monthly_quota: number;
        auto_create_users: boolean;
        blocking_enabled: boolean;
        show_balance: boolean;
        safe_release_enabled: boolean;
      }>("/settings", token)
        .then((data) => {
          setDefaultQuota(data.default_monthly_quota);
          setAutoCreateUsers(data.auto_create_users);
          setBlockingEnabled(data.blocking_enabled);
          setShowBalance(data.show_balance);
          setSafeReleaseEnabled(data.safe_release_enabled);
        })
        .catch((err) => {
          console.error("Erro ao buscar configurações no servidor:", err);
        });
    }

    if (typeof window !== "undefined") {
      const url = localStorage.getItem("settings_apiUrl");
      if (url) setApiUrl(url);

      const srv = localStorage.getItem("settings_ldapServer");
      if (srv) setLdapServer(srv);
      const dn = localStorage.getItem("settings_ldapBindDn");
      if (dn) setLdapBindDn(dn);
      const pwd = localStorage.getItem("settings_ldapBindPassword");
      if (pwd) setLdapBindPassword(pwd);
      const sb = localStorage.getItem("settings_ldapSearchBase");
      if (sb) setLdapSearchBase(sb);
    }
  }, []);

  const saveGeneralSettings = async () => {
    setLoading(true);
    setStatusMsg(null);
    const token = localStorage.getItem("token") || "";

    if (typeof window !== "undefined") {
      localStorage.setItem("settings_apiUrl", apiUrl);
      localStorage.setItem("settings_ldapServer", ldapServer);
      localStorage.setItem("settings_ldapBindDn", ldapBindDn);
      localStorage.setItem("settings_ldapBindPassword", ldapBindPassword);
      localStorage.setItem("settings_ldapSearchBase", ldapSearchBase);
    }

    try {
      await apiFetch("/settings", token, {
        method: "PUT",
        body: JSON.stringify({
          default_monthly_quota: defaultQuota,
          auto_create_users: autoCreateUsers,
          blocking_enabled: blockingEnabled,
          show_balance: showBalance,
          safe_release_enabled: safeReleaseEnabled
        })
      });
      setStatusMsg({ text: "Configurações salvas com sucesso no servidor!", type: "success" });
      setTimeout(() => setStatusMsg(null), 3000);
    } catch (err: any) {
      let errorText = err.message || "";
      try {
        const parsed = JSON.parse(err.message);
        if (parsed.detail) errorText = parsed.detail;
      } catch {}
      setStatusMsg({ text: `Erro ao salvar configurações no servidor: ${errorText}`, type: "error" });
    } finally {
      setLoading(false);
    }
  };

  const testLdap = async () => {
    setLoading(true);
    setStatusMsg(null);
    const token = localStorage.getItem("token") || "";
    try {
      const response = await apiFetch<{ success: boolean; message: string }>("/settings/ldap/test", token, {
        method: "POST",
        body: JSON.stringify({
          server: ldapServer,
          bind_dn: ldapBindDn,
          bind_password: ldapBindPassword,
          search_base: ldapSearchBase,
        }),
      });
      if (response.success) {
        setStatusMsg({ text: "Conexão de teste com LDAP bem-sucedida!", type: "success" });
      } else {
        setStatusMsg({ text: response.message || "Erro desconhecido ao testar conexão.", type: "error" });
      }
    } catch (err: any) {
      // Safely parse error message if nested inside an object or simple text
      let errorText = err.message || "";
      try {
        const parsed = JSON.parse(err.message);
        if (parsed.detail) errorText = parsed.detail;
      } catch {}
      setStatusMsg({ text: `Falha na conexão LDAP: ${errorText}`, type: "error" });
    } finally {
      setLoading(false);
    }
  };

  const syncLdap = async () => {
    setLoading(true);
    setStatusMsg(null);
    const token = localStorage.getItem("token") || "";
    try {
      const response = await apiFetch<{
        success: boolean;
        total_synced: number;
        new_users: number;
        updated_users: number;
      }>("/settings/ldap/sync", token, {
        method: "POST",
        body: JSON.stringify({
          server: ldapServer,
          bind_dn: ldapBindDn,
          bind_password: ldapBindPassword,
          search_base: ldapSearchBase,
        }),
      });
      setStatusMsg({
        text: `Sincronização concluída com sucesso! Total sincronizados: ${response.total_synced} (${response.new_users} novos, ${response.updated_users} atualizados).`,
        type: "success",
      });
    } catch (err: any) {
      let errorText = err.message || "";
      try {
        const parsed = JSON.parse(err.message);
        if (parsed.detail) errorText = parsed.detail;
      } catch {}
      setStatusMsg({ text: `Erro ao sincronizar LDAP: ${errorText}`, type: "error" });
    } finally {
      setLoading(false);
    }
  };

  return (
    <ProtectedPage>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Configurações</h1>
          <p className="text-sm text-muted-foreground">Gerencie o comportamento do sistema e integrações com servidores externos.</p>
        </div>
        <Button onClick={saveGeneralSettings} disabled={loading} className="gap-2">
          <Save className="h-4 w-4" />
          Salvar Configurações
        </Button>
      </div>

      {statusMsg && (
        <div
          className={`mb-6 flex items-start gap-2 rounded-lg p-4 text-sm border ${
            statusMsg.type === "success"
              ? "bg-green-50 border-green-200 text-green-800"
              : "bg-red-50 border-red-200 text-red-800"
          }`}
        >
          {statusMsg.type === "success" ? (
            <CheckCircle className="h-5 w-5 shrink-0 text-green-600" />
          ) : (
            <AlertCircle className="h-5 w-5 shrink-0 text-red-600" />
          )}
          <span>{statusMsg.text}</span>
        </div>
      )}

      <div className="grid gap-6 md:grid-cols-2">
        <Surface className="flex flex-col gap-5 p-5">
          <div>
            <h2 className="text-lg font-semibold flex items-center gap-2">
              <span>Geral</span>
            </h2>
            <p className="text-xs text-muted-foreground">Configurações básicas de limites e cotas.</p>
          </div>
          <div className="grid gap-4">
            <label className="text-sm font-medium block">
              Cota padrão mensal (Páginas)
              <Input
                className="mt-1.5"
                type="number"
                value={defaultQuota}
                onChange={(e) => setDefaultQuota(parseInt(e.target.value) || 0)}
              />
            </label>
            <label className="text-sm font-medium block">
              URL da API do Servidor
              <Input
                className="mt-1.5"
                value={apiUrl}
                onChange={(e) => setApiUrl(e.target.value)}
              />
            </label>
            <div className="flex items-center gap-2.5 mt-2 py-1">
              <input
                type="checkbox"
                id="autoCreate"
                className="h-4 w-4 rounded border-gray-300 text-primary focus:ring-primary cursor-pointer"
                checked={autoCreateUsers}
                onChange={(e) => setAutoCreateUsers(e.target.checked)}
              />
              <label htmlFor="autoCreate" className="text-sm font-medium cursor-pointer">
                Criar usuários automaticamente ao receber trabalhos de impressão
              </label>
            </div>
            <div className="flex items-center gap-2.5 mt-2 py-1">
              <input
                type="checkbox"
                id="blockingEnabled"
                className="h-4 w-4 rounded border-gray-300 text-primary focus:ring-primary cursor-pointer"
                checked={blockingEnabled}
                onChange={(e) => setBlockingEnabled(e.target.checked)}
              />
              <label htmlFor="blockingEnabled" className="text-sm font-medium cursor-pointer">
                Habilitar Bloqueio de Impressões (bloquear se saldo/cota for insuficiente)
              </label>
            </div>
            <div className="flex items-center gap-2.5 mt-2 py-1">
              <input
                type="checkbox"
                id="showBalance"
                className="h-4 w-4 rounded border-gray-300 text-primary focus:ring-primary cursor-pointer"
                checked={showBalance}
                onChange={(e) => setShowBalance(e.target.checked)}
              />
              <label htmlFor="showBalance" className="text-sm font-medium cursor-pointer">
                Exibir Saldo Mensal nas Telas (tabelas e formulários)
              </label>
            </div>
            <div className="flex items-center gap-2.5 mt-2 py-1">
              <input
                type="checkbox"
                id="safeRelease"
                className="h-4 w-4 rounded border-gray-300 text-primary focus:ring-primary cursor-pointer"
                checked={safeReleaseEnabled}
                onChange={(e) => setSafeReleaseEnabled(e.target.checked)}
              />
              <label htmlFor="safeRelease" className="text-sm font-medium cursor-pointer">
                Habilitar Liberação Segura (Follow-Me) — impressões ficam em fila até serem liberadas
              </label>
            </div>
          </div>
        </Surface>

        <Surface className="flex flex-col gap-5 p-5">
          <div>
            <h2 className="text-lg font-semibold flex items-center gap-2">
              <Server className="h-5 w-5 text-primary" />
              <span>Integração AD / LDAP</span>
            </h2>
            <p className="text-xs text-muted-foreground">Sincronize usuários e departamentos corporativos diretamente do Active Directory.</p>
          </div>
          <div className="grid gap-4">
            <label className="text-sm font-medium block">
              Servidor LDAP (URL)
              <Input
                className="mt-1.5"
                placeholder="ldap://192.168.1.10:389"
                value={ldapServer}
                onChange={(e) => setLdapServer(e.target.value)}
              />
            </label>
            <label className="text-sm font-medium block">
              DN de Bind (Usuário de busca)
              <Input
                className="mt-1.5"
                placeholder="cn=admin,dc=empresa,dc=local"
                value={ldapBindDn}
                onChange={(e) => setLdapBindDn(e.target.value)}
              />
            </label>
            <label className="text-sm font-medium block">
              Senha de Bind
              <Input
                className="mt-1.5"
                type="password"
                placeholder="••••••••"
                value={ldapBindPassword}
                onChange={(e) => setLdapBindPassword(e.target.value)}
              />
            </label>
            <label className="text-sm font-medium block">
              Base de Pesquisa (Search Base DN)
              <Input
                className="mt-1.5"
                placeholder="dc=empresa,dc=local"
                value={ldapSearchBase}
                onChange={(e) => setLdapSearchBase(e.target.value)}
              />
            </label>

            <div className="flex gap-3 mt-2">
              <Button
                variant="outline"
                className="flex-1 text-xs"
                onClick={testLdap}
                disabled={loading}
              >
                {loading && <RefreshCw className="mr-1.5 h-3.5 w-3.5 animate-spin" />}
                Testar Conexão
              </Button>
              <Button
                className="flex-1 text-xs gap-1.5"
                onClick={syncLdap}
                disabled={loading}
              >
                {loading && <RefreshCw className="mr-1.5 h-3.5 w-3.5 animate-spin" />}
                <RefreshCw className="h-3.5 w-3.5" />
                Sincronizar Agora
              </Button>
            </div>
          </div>
        </Surface>
      </div>
    </ProtectedPage>
  );
}
