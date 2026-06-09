"use client";

import { FormEvent, useEffect, useState } from "react";
import { AlertCircle, CheckCircle, RefreshCw, Save, Server, UploadCloud } from "lucide-react";

import { ProtectedPage } from "@/components/protected-page";
import { Button, Input, Surface } from "@/components/ui";
import { apiFetch, API_URL } from "@/lib/api";

type PrinterInfo = {
  id: number;
  name: string;
  is_color: boolean;
  is_active: boolean;
};

export default function SettingsPage() {
  const [defaultQuota, setDefaultQuota] = useState(500);
  const [apiUrl, setApiUrl] = useState("http://localhost:8000");
  const [autoCreateUsers, setAutoCreateUsers] = useState(true);
  const [blockingEnabled, setBlockingEnabled] = useState(true);
  const [showBalance, setShowBalance] = useState(true);
  const [safeReleaseEnabled, setSafeReleaseEnabled] = useState(true);

  const [ldapServer, setLdapServer] = useState("ldap://localhost:389");
  const [ldapBindDn, setLdapBindDn] = useState("cn=admin,dc=example,dc=com");
  const [ldapBindPassword, setLdapBindPassword] = useState("secret");
  const [ldapSearchBase, setLdapSearchBase] = useState("dc=example,dc=com");

  const [printers, setPrinters] = useState<PrinterInfo[]>([]);
  const [selectedPrinterId, setSelectedPrinterId] = useState("");
  const [isColorPrint, setIsColorPrint] = useState(false);
  const [fileToPrint, setFileToPrint] = useState<File | null>(null);
  const [webPrintStatus, setWebPrintStatus] = useState<{ text: string; type: "success" | "error" } | null>(null);
  const [webPrintLoading, setWebPrintLoading] = useState(false);

  const [statusMsg, setStatusMsg] = useState<{ text: string; type: "success" | "error" } | null>(null);
  const [loading, setLoading] = useState(false);

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
        .catch((err) => console.error("Erro ao buscar configuracoes no servidor:", err));

      apiFetch<PrinterInfo[]>("/printers", token)
        .then((data) => {
          const activePrinters = data.filter((printer) => printer.is_active);
          setPrinters(activePrinters);
          if (activePrinters.length > 0) {
            setSelectedPrinterId(activePrinters[0].id.toString());
          }
        })
        .catch(() => setPrinters([]));
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
          safe_release_enabled: safeReleaseEnabled,
        }),
      });
      setStatusMsg({ text: "Configuracoes salvas com sucesso.", type: "success" });
      setTimeout(() => setStatusMsg(null), 3000);
    } catch (err: any) {
      setStatusMsg({ text: `Erro ao salvar configuracoes: ${readError(err)}`, type: "error" });
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
      setStatusMsg({
        text: response.success ? "Conexao de teste com LDAP bem-sucedida." : response.message || "Erro desconhecido ao testar conexao.",
        type: response.success ? "success" : "error",
      });
    } catch (err: any) {
      setStatusMsg({ text: `Falha na conexao LDAP: ${readError(err)}`, type: "error" });
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
        text: `Sincronizacao concluida: ${response.total_synced} usuario(s), ${response.new_users} novo(s), ${response.updated_users} atualizado(s).`,
        type: "success",
      });
    } catch (err: any) {
      setStatusMsg({ text: `Erro ao sincronizar LDAP: ${readError(err)}`, type: "error" });
    } finally {
      setLoading(false);
    }
  };

  const selectedPrinter = printers.find((printer) => printer.id.toString() === selectedPrinterId);

  const submitWebPrint = async (event: FormEvent) => {
    event.preventDefault();
    if (!selectedPrinterId || !fileToPrint) {
      setWebPrintStatus({ text: "Selecione uma impressora e escolha um PDF.", type: "error" });
      return;
    }

    setWebPrintLoading(true);
    setWebPrintStatus(null);
    const token = localStorage.getItem("token") || "";
    const formData = new FormData();
    formData.append("file", fileToPrint);
    formData.append("printer_id", selectedPrinterId);
    formData.append("is_color", isColorPrint ? "true" : "false");

    try {
      const response = await fetch(`${API_URL}/jobs/web-print`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: formData,
      });

      if (!response.ok) {
        const detail = await response.text();
        let errorMsg = `Erro ${response.status}`;
        try {
          const parsed = JSON.parse(detail);
          if (parsed.detail) errorMsg = parsed.detail;
        } catch {}
        throw new Error(errorMsg);
      }

      const decision = await response.json();
      if (decision.authorized || decision.status === "pending_release") {
        setWebPrintStatus({
          text: decision.status === "pending_release" ? "Documento enviado para a fila de liberacao." : "Documento enviado para impressao.",
          type: "success",
        });
        setFileToPrint(null);
        const fileInput = document.getElementById("settings-web-print-file") as HTMLInputElement;
        if (fileInput) fileInput.value = "";
      } else {
        setWebPrintStatus({ text: `Impressao bloqueada: ${decision.reason || "Saldo ou cota insuficiente"}`, type: "error" });
      }
    } catch (err: any) {
      setWebPrintStatus({ text: `Falha no Web Print: ${readError(err)}`, type: "error" });
    } finally {
      setWebPrintLoading(false);
    }
  };

  return (
    <ProtectedPage>
      <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Configuracoes</h1>
          <p className="mt-1 text-sm text-muted-foreground">Parametros gerais, integracoes e modulos opcionais.</p>
        </div>
        <Button onClick={saveGeneralSettings} disabled={loading} className="gap-2">
          <Save className="h-4 w-4" />
          Salvar configuracoes
        </Button>
      </div>

      {statusMsg && (
        <div
          className={`mb-6 flex items-start gap-2 rounded-lg border p-4 text-sm ${
            statusMsg.type === "success" ? "border-green-200 bg-green-50 text-green-800" : "border-red-200 bg-red-50 text-red-800"
          }`}
        >
          {statusMsg.type === "success" ? <CheckCircle className="h-5 w-5 shrink-0 text-green-600" /> : <AlertCircle className="h-5 w-5 shrink-0 text-red-600" />}
          <span>{statusMsg.text}</span>
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        <Surface className="p-5">
          <div className="mb-5">
            <h2 className="text-lg font-semibold">Geral</h2>
            <p className="text-xs text-muted-foreground">Regras basicas de cota, bloqueio e criacao automatica.</p>
          </div>
          <div className="grid gap-4">
            <label className="text-sm font-medium">
              Cota padrao mensal
              <Input className="mt-1.5" type="number" value={defaultQuota} onChange={(event) => setDefaultQuota(parseInt(event.target.value) || 0)} />
            </label>
            <label className="text-sm font-medium">
              URL da API do servidor
              <Input className="mt-1.5" value={apiUrl} onChange={(event) => setApiUrl(event.target.value)} />
            </label>
            <ToggleRow id="autoCreate" checked={autoCreateUsers} onChange={setAutoCreateUsers} label="Criar usuarios automaticamente ao receber trabalhos" />
            <ToggleRow id="blockingEnabled" checked={blockingEnabled} onChange={setBlockingEnabled} label="Habilitar bloqueio por cota ou saldo insuficiente" />
            <ToggleRow id="showBalance" checked={showBalance} onChange={setShowBalance} label="Exibir saldo mensal nas telas" />
            <ToggleRow id="safeRelease" checked={safeReleaseEnabled} onChange={setSafeReleaseEnabled} label="Habilitar liberacao segura Follow-Me" />
          </div>
        </Surface>

        <Surface className="p-5">
          <div className="mb-5 flex items-start gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-md bg-primary/10 text-primary">
              <Server className="h-5 w-5" />
            </div>
            <div>
              <h2 className="text-lg font-semibold">Integracao AD / LDAP</h2>
              <p className="text-xs text-muted-foreground">Sincronizacao de usuarios e departamentos corporativos.</p>
            </div>
          </div>
          <div className="grid gap-4">
            <label className="text-sm font-medium">
              Servidor LDAP
              <Input className="mt-1.5" placeholder="ldap://192.168.1.10:389" value={ldapServer} onChange={(event) => setLdapServer(event.target.value)} />
            </label>
            <label className="text-sm font-medium">
              DN de bind
              <Input className="mt-1.5" placeholder="cn=admin,dc=empresa,dc=local" value={ldapBindDn} onChange={(event) => setLdapBindDn(event.target.value)} />
            </label>
            <label className="text-sm font-medium">
              Senha de bind
              <Input className="mt-1.5" type="password" value={ldapBindPassword} onChange={(event) => setLdapBindPassword(event.target.value)} />
            </label>
            <label className="text-sm font-medium">
              Base de pesquisa
              <Input className="mt-1.5" placeholder="dc=empresa,dc=local" value={ldapSearchBase} onChange={(event) => setLdapSearchBase(event.target.value)} />
            </label>
            <div className="mt-2 flex gap-3">
              <Button variant="outline" className="flex-1 text-xs" onClick={testLdap} disabled={loading}>
                {loading && <RefreshCw className="h-3.5 w-3.5 animate-spin" />}
                Testar conexao
              </Button>
              <Button className="flex-1 text-xs" onClick={syncLdap} disabled={loading}>
                <RefreshCw className="h-3.5 w-3.5" />
                Sincronizar agora
              </Button>
            </div>
          </div>
        </Surface>
      </div>

      <Surface className="mt-6 p-5">
        <details>
          <summary className="flex cursor-pointer list-none items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <div className="flex h-9 w-9 items-center justify-center rounded-md bg-primary/10 text-primary">
                <UploadCloud className="h-5 w-5" />
              </div>
              <div>
                <h2 className="text-lg font-semibold">Modulo Web Print</h2>
                <p className="text-xs text-muted-foreground">Envio manual de PDF pelo navegador, para uso eventual.</p>
              </div>
            </div>
            <span className="rounded-full bg-muted px-2.5 py-1 text-xs font-semibold text-muted-foreground">Opcional</span>
          </summary>

          <form onSubmit={submitWebPrint} className="mt-5 grid gap-4 lg:grid-cols-[1fr_1fr_auto] lg:items-end">
            <label className="grid gap-1.5 text-xs font-semibold text-muted-foreground">
              Impressora
              <select
                value={selectedPrinterId}
                onChange={(event) => {
                  setSelectedPrinterId(event.target.value);
                  const printer = printers.find((item) => item.id.toString() === event.target.value);
                  if (printer && !printer.is_color) setIsColorPrint(false);
                }}
                className="h-9 w-full rounded-md border bg-white px-3 text-sm text-foreground outline-none focus-visible:border-primary focus-visible:ring-2 focus-visible:ring-ring/20"
                required
              >
                <option value="" disabled>
                  Selecione uma impressora
                </option>
                {printers.map((printer) => (
                  <option key={printer.id} value={printer.id}>
                    {printer.name} {printer.is_color ? "(colorida)" : "(P&B)"}
                  </option>
                ))}
              </select>
            </label>

            <label className="grid gap-1.5 text-xs font-semibold text-muted-foreground">
              Documento PDF
              <input
                id="settings-web-print-file"
                type="file"
                accept=".pdf"
                onChange={(event) => setFileToPrint(event.target.files?.[0] || null)}
                className="h-9 w-full rounded-md border bg-white px-3 py-1 text-sm text-foreground outline-none file:mr-4 file:rounded-md file:border-0 file:bg-primary file:px-2.5 file:py-0.5 file:text-xs file:font-semibold file:text-primary-foreground"
                required
              />
            </label>

            <div className="flex items-center gap-3">
              <label className={`flex items-center gap-2 whitespace-nowrap text-sm font-medium ${selectedPrinter && !selectedPrinter.is_color ? "opacity-50" : ""}`}>
                <input
                  type="checkbox"
                  className="h-4 w-4"
                  checked={isColorPrint}
                  disabled={!selectedPrinter?.is_color}
                  onChange={(event) => setIsColorPrint(event.target.checked)}
                />
                Colorida
              </label>
              <Button type="submit" disabled={webPrintLoading || !fileToPrint}>
                {webPrintLoading ? "Enviando..." : "Enviar"}
              </Button>
            </div>
          </form>

          {webPrintStatus ? (
            <div
              className={`mt-4 rounded-md border p-3 text-sm font-semibold ${
                webPrintStatus.type === "success" ? "border-green-200 bg-green-50 text-green-800" : "border-red-200 bg-red-50 text-red-800"
              }`}
            >
              {webPrintStatus.text}
            </div>
          ) : null}
        </details>
      </Surface>
    </ProtectedPage>
  );
}

function ToggleRow({ id, checked, onChange, label }: { id: string; checked: boolean; onChange: (value: boolean) => void; label: string }) {
  return (
    <div className="flex items-center gap-2.5 py-1">
      <input
        id={id}
        type="checkbox"
        className="h-4 w-4 rounded border-gray-300 text-primary focus:ring-primary"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
      />
      <label htmlFor={id} className="cursor-pointer text-sm font-medium">
        {label}
      </label>
    </div>
  );
}

function readError(err: any) {
  let errorText = err?.message || "";
  try {
    const parsed = JSON.parse(errorText);
    if (parsed.detail) errorText = parsed.detail;
  } catch {}
  return errorText || "Erro desconhecido";
}
