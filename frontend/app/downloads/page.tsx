"use client";

import { useEffect, useState } from "react";
import { Check, Copy, Download, FileArchive, RefreshCw, ShieldCheck, TerminalSquare } from "lucide-react";

import { ProtectedPage } from "@/components/protected-page";
import { Button, Input, Surface } from "@/components/ui";
import { API_URL, apiFetch, getCurrentRole } from "@/lib/api";

type ReleaseFile = {
  kind: string;
  filename: string;
  size_bytes: number;
  sha256: string;
  signature_status: string | null;
  signer_subject: string | null;
  download_url: string;
};

type AgentRelease = {
  version: string;
  channel: string;
  published_at: string | null;
  notes: string | null;
  checksums_url: string | null;
  signature_status: string;
  signature_summary: string;
  files: ReleaseFile[];
};

type OrganizationOption = {
  id: number;
  name: string;
  slug: string;
  is_active: boolean;
  billing_status: "trial" | "active" | "past_due" | "suspended";
};

function formatBytes(value: number) {
  if (value > 1024 * 1024) return `${(value / 1024 / 1024).toFixed(1)} MB`;
  if (value > 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${value} B`;
}

function signatureClass(status: string | null) {
  if (status === "Valid") return "border-emerald-200 bg-emerald-50 text-emerald-700";
  if (!status || status === "NotSigned") return "border-amber-200 bg-amber-50 text-amber-700";
  return "border-red-200 bg-red-50 text-red-700";
}

function signatureLabel(status: string | null) {
  if (status === "Valid") return "Assinado";
  if (!status || status === "NotSigned") return "Sem assinatura";
  return status;
}

function releaseSignatureClass(status: string) {
  if (status === "signed") return "border-emerald-200 bg-emerald-50 text-emerald-700";
  if (status === "mixed") return "border-amber-200 bg-amber-50 text-amber-700";
  if (status === "unsigned") return "border-slate-200 bg-slate-100 text-slate-700";
  return "border-red-200 bg-red-50 text-red-700";
}

function releaseSignatureLabel(status: string) {
  if (status === "signed") return "Release assinada";
  if (status === "mixed") return "Assinatura parcial";
  if (status === "unsigned") return "Sem assinatura";
  if (status === "empty") return "Sem arquivos";
  return "Assinatura com alerta";
}

function billingStatusSuffix(status: OrganizationOption["billing_status"]) {
  if (status === "past_due") return " - em atraso";
  if (status === "trial") return " - teste";
  if (status === "suspended") return " - suspensa";
  return "";
}

function maskSecret(command: string, secret: string) {
  if (!command || !secret) return command;
  return command.replaceAll(secret, "********");
}

export default function DownloadsPage() {
  const [releases, setReleases] = useState<AgentRelease[]>([]);
  const [organizations, setOrganizations] = useState<OrganizationOption[]>([]);
  const [isAdmin, setIsAdmin] = useState(false);
  const [loading, setLoading] = useState(false);
  const [deployOrg, setDeployOrg] = useState("default");
  const [deployUser, setDeployUser] = useState("agent");
  const [deployPassword, setDeployPassword] = useState("");
  const [defaultUsername, setDefaultUsername] = useState("");
  const [spoolServer, setSpoolServer] = useState("");
  const [logLevel, setLogLevel] = useState("INFO");
  const [cancelBlocked, setCancelBlocked] = useState(true);
  const [usePrintEventLog, setUsePrintEventLog] = useState(true);
  const [autoUpdate, setAutoUpdate] = useState(true);
  const [copiedCommand, setCopiedCommand] = useState<"exe" | "msi" | null>(null);
  const [copiedSha, setCopiedSha] = useState<string | null>(null);
  const [downloadError, setDownloadError] = useState<string | null>(null);

  async function load() {
    const token = localStorage.getItem("token");
    if (!token) return;
    setLoading(true);
    try {
      const data = await apiFetch<AgentRelease[]>("/agent/releases", token);
      setReleases(data);
      const canPrepareDeployment = getCurrentRole(token) === "admin";
      const orgs = canPrepareDeployment ? await apiFetch<OrganizationOption[]>("/agent/deployment-organizations", token).catch(() => []) : [];
      setOrganizations(orgs);
      const currentSlug = localStorage.getItem("organization_slug") || "default";
      if (orgs.length > 0 && !orgs.some((organization) => organization.slug === deployOrg)) {
        const preferred =
          orgs.find((organization) => organization.slug === currentSlug && organization.is_active) ??
          orgs.find((organization) => organization.is_active) ??
          orgs[0];
        setDeployOrg(preferred.slug);
      }
    } catch {
      setReleases([]);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    const token = localStorage.getItem("token");
    setIsAdmin(token ? getCurrentRole(token) === "admin" : false);
    setDeployOrg(localStorage.getItem("organization_slug") || "default");
    load();
  }, []);

  async function downloadFile(file: ReleaseFile) {
    const token = localStorage.getItem("token");
    if (!token) return;
    try {
      setDownloadError(null);
      await downloadBlob(file.download_url, file.filename, token);
    } catch (error) {
      setDownloadError(error instanceof Error ? error.message : "Nao foi possivel baixar o arquivo.");
    }
  }

  async function downloadChecksums(release: AgentRelease) {
    if (!release.checksums_url) return;
    const token = localStorage.getItem("token");
    if (!token) return;
    try {
      setDownloadError(null);
      await downloadBlob(release.checksums_url, `SHA256SUMS-${release.version}.txt`, token);
    } catch (error) {
      setDownloadError(error instanceof Error ? error.message : "Nao foi possivel baixar os checksums.");
    }
  }

  async function downloadBlob(path: string, filename: string, token: string) {
    const response = await fetch(`${API_URL}${path}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!response.ok) {
      const detail = await response.text().catch(() => "");
      const message = detail.trim() || `HTTP ${response.status}`;
      throw new Error(`Falha ao baixar ${filename}: ${message}`);
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    link.click();
    URL.revokeObjectURL(url);
  }

  async function copyCommand(kind: "exe" | "msi", command: string) {
    await navigator.clipboard.writeText(command);
    setCopiedCommand(kind);
    window.setTimeout(() => setCopiedCommand(null), 1800);
  }

  async function copySha(file: ReleaseFile) {
    await navigator.clipboard.writeText(file.sha256);
    setCopiedSha(file.filename);
    window.setTimeout(() => setCopiedSha(null), 1800);
  }

  const latest = releases[0];
  const installerFile = latest?.files.find((file) => file.kind === "installer" || file.filename.toLowerCase().endsWith("installer.exe"));
  const msiFile = latest?.files.find((file) => file.kind === "msi" || file.filename.toLowerCase().endsWith(".msi"));
  const selectedOrganization = organizations.find((organization) => organization.slug === deployOrg);
  const selectedOrganizationActive = organizations.length === 0 || selectedOrganization?.is_active === true;
  const commandReady = Boolean(deployOrg.trim() && deployUser.trim() && deployPassword.trim() && selectedOrganizationActive);
  const commandMissingMessage = selectedOrganizationActive
    ? "Informe empresa, usuario e senha do agent para gerar o comando."
    : "Empresa inativa: reative a empresa antes de gerar comando de instalacao.";
  const cancelBlockedArg = cancelBlocked ? "true" : "false";
  const usePrintEventLogArg = usePrintEventLog ? "true" : "false";
  const autoUpdateArg = autoUpdate ? "true" : "false";
  const exeCommand = installerFile && commandReady
    ? `.\\${installerFile.filename} --silent --api-url "${API_URL}" --username "${deployUser}" --password "${deployPassword}" --organization "${deployOrg}" --default-username "${defaultUsername}" --spool-server "${spoolServer}" --log-level "${logLevel}" --cancel-blocked "${cancelBlockedArg}" --use-print-event-log "${usePrintEventLogArg}" --auto-update "${autoUpdateArg}"`
    : "";
  const msiCommand = msiFile && commandReady
    ? `msiexec /i "${msiFile.filename}" APIURL="${API_URL}" AGENTUSER="${deployUser}" AGENTPASSWORD="${deployPassword}" ORGANIZATION="${deployOrg}" DEFAULTUSERNAME="${defaultUsername}" SPOOLSERVER="${spoolServer}" LOGLEVEL="${logLevel}" CANCELBLOCKED="${cancelBlockedArg}" USEPRINTEVENTLOG="${usePrintEventLogArg}" AUTOUPDATE="${autoUpdateArg}" /qn`
    : "";

  return (
    <ProtectedPage>
      <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Downloads</h1>
          <p className="mt-1 text-sm text-muted-foreground">Versoes publicadas do agent, instalador, MSI e checksums SHA256.</p>
        </div>
        <Button variant="outline" onClick={load} disabled={loading}>
          <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
          Atualizar
        </Button>
      </div>

      {isAdmin ? (
        <Surface className="mb-6 p-4">
          <div className="mb-4 flex items-start gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-md bg-primary/10 text-primary">
              <TerminalSquare className="h-5 w-5" />
            </div>
            <div>
              <h2 className="text-sm font-bold">Instalacao silenciosa</h2>
              <p className="text-xs text-muted-foreground">Comandos prontos para implantar o agent. A senha fica mascarada na tela, mas e copiada corretamente.</p>
            </div>
          </div>
          <div className="mb-4 grid gap-3 md:grid-cols-4">
            <label className="grid gap-1.5 text-xs font-semibold text-muted-foreground">
              API
              <Input value={API_URL} readOnly />
            </label>
            <label className="grid gap-1.5 text-xs font-semibold text-muted-foreground">
              Empresa
              {organizations.length > 0 ? (
                <select
                  className="h-9 rounded-md border bg-white px-3 text-sm text-foreground outline-none focus-visible:border-primary focus-visible:ring-2 focus-visible:ring-ring/20"
                  value={deployOrg}
                  onChange={(event) => setDeployOrg(event.target.value)}
                >
                  {organizations.map((organization) => (
                    <option key={organization.id} value={organization.slug} disabled={!organization.is_active}>
                      {organization.name} ({organization.slug}){organization.is_active ? billingStatusSuffix(organization.billing_status) : " - inativa"}
                    </option>
                  ))}
                </select>
              ) : (
                <Input value={deployOrg} onChange={(event) => setDeployOrg(event.target.value)} />
              )}
            </label>
            <label className="grid gap-1.5 text-xs font-semibold text-muted-foreground">
              Usuario agent
              <Input value={deployUser} onChange={(event) => setDeployUser(event.target.value)} />
            </label>
            <label className="grid gap-1.5 text-xs font-semibold text-muted-foreground">
              Senha agent
              <Input type="password" value={deployPassword} onChange={(event) => setDeployPassword(event.target.value)} />
            </label>
          </div>
          <div className="mb-4 grid gap-3 md:grid-cols-3">
            <label className="grid gap-1.5 text-xs font-semibold text-muted-foreground">
              Usuario padrao do PC
              <Input placeholder="Opcional" value={defaultUsername} onChange={(event) => setDefaultUsername(event.target.value)} />
            </label>
            <label className="grid gap-1.5 text-xs font-semibold text-muted-foreground">
              Servidor de impressao
              <Input placeholder="Opcional: \\SRV-PRINT01" value={spoolServer} onChange={(event) => setSpoolServer(event.target.value)} />
            </label>
            <label className="grid gap-1.5 text-xs font-semibold text-muted-foreground">
              Modo de log
              <select
                className="h-9 rounded-md border bg-white px-3 text-sm text-foreground outline-none focus-visible:border-primary focus-visible:ring-2 focus-visible:ring-ring/20"
                value={logLevel}
                onChange={(event) => setLogLevel(event.target.value)}
              >
                <option value="INFO">INFO</option>
                <option value="DEBUG">DEBUG</option>
                <option value="WARNING">WARNING</option>
                <option value="ERROR">ERROR</option>
                <option value="CRITICAL">CRITICAL</option>
              </select>
            </label>
          </div>
          <div className="mb-4 grid gap-2 md:grid-cols-3">
            <label className="flex items-center gap-2 rounded-md border bg-white px-3 py-2 text-xs font-semibold text-muted-foreground">
              <input type="checkbox" checked={cancelBlocked} onChange={(event) => setCancelBlocked(event.target.checked)} />
              Cancelar bloqueados
            </label>
            <label className="flex items-center gap-2 rounded-md border bg-white px-3 py-2 text-xs font-semibold text-muted-foreground">
              <input type="checkbox" checked={usePrintEventLog} onChange={(event) => setUsePrintEventLog(event.target.checked)} />
              Usar Event Log
            </label>
            <label className="flex items-center gap-2 rounded-md border bg-white px-3 py-2 text-xs font-semibold text-muted-foreground">
              <input type="checkbox" checked={autoUpdate} onChange={(event) => setAutoUpdate(event.target.checked)} />
              Auto-update
            </label>
          </div>
          <div className="grid gap-3 lg:grid-cols-2">
            <CommandBox
              title="EXE"
              command={exeCommand}
              displayCommand={maskSecret(exeCommand, deployPassword)}
              disabled={!installerFile || !commandReady}
              emptyMessage={!installerFile ? undefined : commandMissingMessage}
              copied={copiedCommand === "exe"}
              onCopy={() => copyCommand("exe", exeCommand)}
            />
            <CommandBox
              title="MSI"
              command={msiCommand}
              displayCommand={maskSecret(msiCommand, deployPassword)}
              disabled={!msiFile || !commandReady}
              emptyMessage={!msiFile ? undefined : commandMissingMessage}
              copied={copiedCommand === "msi"}
              onCopy={() => copyCommand("msi", msiCommand)}
            />
          </div>
        </Surface>
      ) : null}

      {downloadError ? (
        <Surface className="mb-6 border-red-200 bg-red-50 p-4 text-sm font-semibold text-red-700">{downloadError}</Surface>
      ) : null}

      <Surface className="overflow-hidden">
        {releases.length === 0 ? (
          <div className="p-8 text-center text-sm text-muted-foreground">Nenhuma versao publicada no manifest.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-muted/80 text-left text-xs uppercase tracking-wide text-muted-foreground">
                <tr>
                  <th className="p-4">Versao</th>
                  <th className="p-4">Arquivo</th>
                  <th className="p-4">Tipo</th>
                  <th className="p-4">Assinatura</th>
                  <th className="p-4 text-right">Tamanho</th>
                  <th className="p-4">SHA256</th>
                  <th className="p-4 text-right">Download</th>
                </tr>
              </thead>
              <tbody>
                {releases.flatMap((release) =>
                  release.files.map((file) => (
                    <tr key={`${release.version}-${file.filename}`} className="border-t bg-white hover:bg-muted/30">
                      <td className="p-4">
                        <div className="font-semibold">{release.version}</div>
                        <div className="text-xs text-muted-foreground">{release.channel}</div>
                        <span
                          className={`mt-2 inline-flex rounded-full border px-2 py-0.5 text-xs font-semibold ${releaseSignatureClass(release.signature_status)}`}
                          title={release.signature_summary}
                        >
                          {releaseSignatureLabel(release.signature_status)}
                        </span>
                        <Button
                          variant="outline"
                          className="mt-2 h-7 px-2 text-xs"
                          onClick={() => downloadChecksums(release)}
                          disabled={!release.checksums_url}
                        >
                          <Download className="h-3.5 w-3.5" />
                          Checksums
                        </Button>
                      </td>
                      <td className="p-4">
                        <div className="flex items-center gap-2 font-medium">
                          <FileArchive className="h-4 w-4 text-primary" />
                          {file.filename}
                        </div>
                        {release.notes ? <div className="mt-1 text-xs text-muted-foreground">{release.notes}</div> : null}
                      </td>
                      <td className="p-4">
                        <span className="inline-flex items-center gap-1 rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-xs font-semibold text-emerald-700">
                          <ShieldCheck className="h-3 w-3" />
                          {file.kind}
                        </span>
                      </td>
                      <td className="p-4">
                        <span
                          className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-semibold ${signatureClass(file.signature_status)}`}
                          title={file.signer_subject || undefined}
                        >
                          {signatureLabel(file.signature_status)}
                        </span>
                      </td>
                      <td className="p-4 text-right">{formatBytes(file.size_bytes)}</td>
                      <td className="max-w-[380px] p-4">
                        <div className="flex items-center gap-2">
                          <span className="truncate font-mono text-xs" title={file.sha256}>
                            {file.sha256}
                          </span>
                          <Button variant="outline" className="h-7 shrink-0 px-2 text-xs" onClick={() => copySha(file)} title="Copiar SHA256">
                            {copiedSha === file.filename ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
                            {copiedSha === file.filename ? "Copiado" : "Copiar"}
                          </Button>
                        </div>
                      </td>
                      <td className="p-4 text-right">
                        <Button onClick={() => downloadFile(file)}>
                          <Download className="h-4 w-4" />
                          Baixar
                        </Button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        )}
      </Surface>
    </ProtectedPage>
  );
}

function CommandBox({
  title,
  command,
  displayCommand,
  disabled,
  copied,
  onCopy,
  emptyMessage,
}: {
  title: string;
  command: string;
  displayCommand: string;
  disabled: boolean;
  copied: boolean;
  onCopy: () => void;
  emptyMessage?: string;
}) {
  return (
    <div className="rounded-md border bg-muted/20 p-3">
      <div className="mb-2 flex items-center justify-between gap-2">
        <div className="text-xs font-bold uppercase text-muted-foreground">{title}</div>
        <Button variant="outline" className="h-8 px-2 text-xs" onClick={onCopy} disabled={disabled || !command}>
          {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
          {copied ? "Copiado" : "Copiar"}
        </Button>
      </div>
      <pre className="min-h-[72px] overflow-auto whitespace-pre-wrap rounded-md bg-slate-950 p-3 font-mono text-xs text-slate-100">
        {disabled ? emptyMessage ?? `Nenhum arquivo ${title} publicado no manifest.` : displayCommand}
      </pre>
    </div>
  );
}
