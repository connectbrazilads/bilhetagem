"use client";

import { useCallback, useEffect, useState, type ComponentType } from "react";
import { CalendarClock, Check, Copy, Download, FileArchive, PackageCheck, RefreshCw, ShieldCheck, TerminalSquare } from "lucide-react";

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
  checksums_sha256: string | null;
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
  agent_username: string | null;
  enrollment_key_created_at: string | null;
};

type EnrollmentKeyResponse = {
  organization_id: number;
  organization_name: string;
  organization_slug: string;
  enrollment_key: string;
  created_at: string;
};

type CopiedCommand =
  | "exe"
  | "msi"
  | "build-release"
  | "publish-release"
  | "reload-release"
  | "public-installer"
  | "activation-key"
  | "activation-command"
  | null;

const UNSAFE_AGENT_PASSWORDS = new Set([
  "",
  "admin",
  "agent",
  "agent12345",
  "admin12345",
  "change-me-agent-password",
  "change-me-admin-password",
  "password",
  "senha123",
  "12345678",
]);

function formatBytes(value: number) {
  if (value > 1024 * 1024) return `${(value / 1024 / 1024).toFixed(1)} MB`;
  if (value > 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${value} B`;
}

function formatDateTime(value: string | null) {
  if (!value) return "Sem data";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Data invalida";
  return new Intl.DateTimeFormat("pt-BR", {
    dateStyle: "short",
    timeStyle: "short",
  }).format(date);
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

function artifactKindLabel(kind: string, filename: string) {
  const normalizedKind = kind.toLowerCase();
  const normalizedFilename = filename.toLowerCase();
  if (normalizedKind === "installer" || normalizedFilename.endsWith("installer.exe")) return "Instalador EXE";
  if (normalizedKind === "msi" || normalizedFilename.endsWith(".msi")) return "Instalador MSI";
  if (normalizedKind === "agent") return "Agent";
  if (normalizedKind === "checksums") return "Checksums";
  return kind;
}

function artifactKindClass(kind: string, filename: string) {
  const label = artifactKindLabel(kind, filename);
  if (label === "Instalador EXE" || label === "Instalador MSI") return "border-blue-200 bg-blue-50 text-blue-700";
  if (label === "Agent") return "border-emerald-200 bg-emerald-50 text-emerald-700";
  if (label === "Checksums") return "border-slate-200 bg-slate-100 text-slate-700";
  return "border-amber-200 bg-amber-50 text-amber-700";
}

function billingStatusSuffix(status: OrganizationOption["billing_status"]) {
  if (status === "past_due") return " - em atraso";
  if (status === "trial") return " - teste";
  if (status === "suspended") return " - suspensa";
  return "";
}

function powershellQuote(value: string) {
  return `'${value.replaceAll("'", "''")}'`;
}

function msiProperty(name: string, value: string) {
  return `${name}=${powershellQuote(value)}`;
}

function maskSecret(command: string, secret: string) {
  if (!command || !secret) return command;
  return command.replaceAll(secret, "********").replaceAll(powershellQuote(secret), "'********'");
}

function isUnsafeAgentPassword(value: string) {
  return UNSAFE_AGENT_PASSWORDS.has(value.trim().toLowerCase());
}

function isValidOrganizationSlug(value: string) {
  return /^[a-z0-9][a-z0-9-]*[a-z0-9]$/.test(value.trim().toLowerCase());
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
  const [snmpCommunity, setSnmpCommunity] = useState("public");
  const [snmpPollInterval, setSnmpPollInterval] = useState("60");
  const [snmpTimeout, setSnmpTimeout] = useState("2.0");
  const [snmpRetries, setSnmpRetries] = useState("1");
  const [logLevel, setLogLevel] = useState("INFO");
  const [cancelBlocked, setCancelBlocked] = useState(true);
  const [usePrintEventLog, setUsePrintEventLog] = useState(true);
  const [autoUpdate, setAutoUpdate] = useState(true);
  const [copiedCommand, setCopiedCommand] = useState<CopiedCommand>(null);
  const [copiedSha, setCopiedSha] = useState<string | null>(null);
  const [downloadError, setDownloadError] = useState<string | null>(null);
  const [activationKey, setActivationKey] = useState("");
  const [generatingKey, setGeneratingKey] = useState(false);

  const load = useCallback(async () => {
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
      setDeployOrg((current) => {
        if (orgs.length === 0) return current;
        const currentOrganization = orgs.find((organization) => organization.slug === current);
        if (currentOrganization) {
          if (currentOrganization.agent_username) setDeployUser(currentOrganization.agent_username);
          return current;
        }
        const preferred =
          orgs.find((organization) => organization.slug === currentSlug && organization.is_active) ??
          orgs.find((organization) => organization.is_active) ??
          orgs[0];
        if (preferred.agent_username) setDeployUser(preferred.agent_username);
        return preferred.slug;
      });
    } catch {
      setReleases([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const token = localStorage.getItem("token");
    setIsAdmin(token ? getCurrentRole(token) === "admin" : false);
    setDeployOrg(localStorage.getItem("organization_slug") || "default");
    load();
  }, [load]);

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

  async function copyCommand(kind: Exclude<CopiedCommand, null>, command: string) {
    await navigator.clipboard.writeText(command);
    setCopiedCommand(kind);
    window.setTimeout(() => setCopiedCommand(null), 1800);
  }

  async function copySha(file: ReleaseFile, releaseVersion: string) {
    await navigator.clipboard.writeText(file.sha256);
    setCopiedSha(`${releaseVersion}:${file.filename}`);
    window.setTimeout(() => setCopiedSha(null), 1800);
  }

  async function copyChecksumsSha(release: AgentRelease) {
    if (!release.checksums_sha256) return;
    await navigator.clipboard.writeText(release.checksums_sha256);
    setCopiedSha(`${release.version}:SHA256SUMS`);
    window.setTimeout(() => setCopiedSha(null), 1800);
  }

  async function rotateEnrollmentKey() {
    const token = localStorage.getItem("token");
    if (!token || !deployOrg) return;
    setGeneratingKey(true);
    try {
      setDownloadError(null);
      const response = await apiFetch<EnrollmentKeyResponse>(`/agent/deployment-organizations/${deployOrg}/enrollment-key`, token, {
        method: "POST",
      });
      setActivationKey(response.enrollment_key);
      setOrganizations((current) =>
        current.map((organization) =>
          organization.slug === response.organization_slug ? { ...organization, enrollment_key_created_at: response.created_at } : organization
        )
      );
    } catch (error) {
      setDownloadError(error instanceof Error ? error.message : "Nao foi possivel gerar a chave de ativacao.");
    } finally {
      setGeneratingKey(false);
    }
  }

  const latest = releases[0];
  const installerFile = latest?.files.find((file) => file.kind === "installer" || file.filename.toLowerCase().endsWith("installer.exe"));
  const msiFile = latest?.files.find((file) => file.kind === "msi" || file.filename.toLowerCase().endsWith(".msi"));
  const latestTotalSize = latest?.files.reduce((total, file) => total + file.size_bytes, 0) ?? 0;
  const latestInstallerCount = latest?.files.filter((file) => file.kind === "installer" || file.kind === "msi").length ?? 0;
  const latestReadyArtifacts = [
    installerFile ? "EXE" : null,
    msiFile ? "MSI" : null,
    latest?.checksums_url ? "SHA256" : null,
  ].filter(Boolean);
  const releaseIncomplete = !latest || latestInstallerCount === 0 || !latest?.checksums_url;
  const selectedOrganization = organizations.find((organization) => organization.slug === deployOrg);
  const selectedOrganizationActive = organizations.length === 0 || selectedOrganization?.is_active === true;
  const validOrganizationSlug = isValidOrganizationSlug(deployOrg);
  const unsafePassword = isUnsafeAgentPassword(deployPassword);
  const snmpPollIntervalNumber = Number(snmpPollInterval);
  const snmpTimeoutNumber = Number(snmpTimeout.replace(",", "."));
  const snmpRetriesNumber = Number(snmpRetries);
  const snmpSettingsValid =
    Number.isFinite(snmpPollIntervalNumber) &&
    snmpPollIntervalNumber >= 1 &&
    Number.isFinite(snmpTimeoutNumber) &&
    snmpTimeoutNumber >= 0.1 &&
    Number.isFinite(snmpRetriesNumber) &&
    snmpRetriesNumber >= 0;
  const commandReady = Boolean(
    deployOrg.trim() &&
      validOrganizationSlug &&
      deployUser.trim() &&
      deployPassword.trim() &&
      selectedOrganizationActive &&
      !unsafePassword &&
      snmpSettingsValid
  );
  const commandMissingMessage = unsafePassword
    ? "Use uma senha exclusiva para esta empresa; senhas padrao ou placeholders sao bloqueadas."
    : !validOrganizationSlug
    ? "Slug da empresa invalido. Use apenas letras, numeros e hifens, sem espacos."
    : !snmpSettingsValid
    ? "Revise SNMP: intervalo minimo 1s, timeout minimo 0,1s e tentativas a partir de 0."
    : selectedOrganizationActive
    ? "Informe empresa, usuario e senha do agent para gerar o comando."
    : "Empresa inativa: reative a empresa antes de gerar comando de instalacao.";
  const cancelBlockedArg = cancelBlocked ? "true" : "false";
  const usePrintEventLogArg = usePrintEventLog ? "true" : "false";
  const autoUpdateArg = autoUpdate ? "true" : "false";
  const publicInstallerUrl = `${API_URL}/agent/public-installer?kind=installer`;
  const activationCommand =
    installerFile && activationKey
      ? [
          "&",
          powershellQuote(`.\\${installerFile.filename}`),
          "--silent",
          "--api-url",
          powershellQuote(API_URL),
          "--activation-key",
          powershellQuote(activationKey),
          "--default-username",
          powershellQuote(defaultUsername),
          "--spool-server",
          powershellQuote(spoolServer),
          "--snmp-community",
          powershellQuote(snmpCommunity),
          "--snmp-poll-interval",
          powershellQuote(snmpPollInterval),
          "--snmp-timeout",
          powershellQuote(snmpTimeout),
          "--snmp-retries",
          powershellQuote(snmpRetries),
          "--log-level",
          powershellQuote(logLevel),
          "--cancel-blocked",
          powershellQuote(cancelBlockedArg),
          "--use-print-event-log",
          powershellQuote(usePrintEventLogArg),
          "--auto-update",
          powershellQuote(autoUpdateArg),
        ].join(" ")
      : "";
  const buildReleaseCommand = `cd 'C:\\Projetos\\Sistema Bilhetagem\\agent'
.\\build_release.ps1
.\\verify_release.ps1 -RequireMsi -RequireInstaller`;
  const publishReleaseCommand = `# Ajuste o destino para a pasta do projeto na VPS
scp -r '.\\releases\\*' usuario@IP_DA_VPS:/caminho/do/projeto/agent/releases/`;
  const reloadReleaseCommand = `cd /caminho/do/projeto
docker compose up -d --build backend
# Opcional, se a VPS tiver PowerShell:
pwsh ./deploy/preflight-server.ps1 -SkipEndpointChecks`;
  const exeCommand =
    installerFile && commandReady
      ? [
          "&",
          powershellQuote(`.\\${installerFile.filename}`),
          "--silent",
          "--api-url",
          powershellQuote(API_URL),
          "--username",
          powershellQuote(deployUser),
          "--password",
          powershellQuote(deployPassword),
          "--organization",
          powershellQuote(deployOrg),
          "--default-username",
          powershellQuote(defaultUsername),
          "--spool-server",
          powershellQuote(spoolServer),
          "--snmp-community",
          powershellQuote(snmpCommunity),
          "--snmp-poll-interval",
          powershellQuote(snmpPollInterval),
          "--snmp-timeout",
          powershellQuote(snmpTimeout),
          "--snmp-retries",
          powershellQuote(snmpRetries),
          "--log-level",
          powershellQuote(logLevel),
          "--cancel-blocked",
          powershellQuote(cancelBlockedArg),
          "--use-print-event-log",
          powershellQuote(usePrintEventLogArg),
          "--auto-update",
          powershellQuote(autoUpdateArg),
        ].join(" ")
      : "";
  const msiCommand =
    msiFile && commandReady
      ? [
          "msiexec",
          "/i",
          powershellQuote(msiFile.filename),
          msiProperty("APIURL", API_URL),
          msiProperty("AGENTUSER", deployUser),
          msiProperty("AGENTPASSWORD", deployPassword),
          msiProperty("ORGANIZATION", deployOrg),
          msiProperty("DEFAULTUSERNAME", defaultUsername),
          msiProperty("SPOOLSERVER", spoolServer),
          msiProperty("SNMPCOMMUNITY", snmpCommunity),
          msiProperty("SNMPPOLLINTERVAL", snmpPollInterval),
          msiProperty("SNMPTIMEOUT", snmpTimeout),
          msiProperty("SNMPRETRIES", snmpRetries),
          msiProperty("LOGLEVEL", logLevel),
          msiProperty("CANCELBLOCKED", cancelBlockedArg),
          msiProperty("USEPRINTEVENTLOG", usePrintEventLogArg),
          msiProperty("AUTOUPDATE", autoUpdateArg),
          "/qn",
        ].join(" ")
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

      <div className="mb-6 grid gap-3 md:grid-cols-4">
        <ReleaseSummaryCard
          icon={PackageCheck}
          label="Release atual"
          value={latest?.version ?? "-"}
          detail={latest ? `${latest.channel} | ${latest.files.length.toLocaleString("pt-BR")} arquivo(s)` : "Nenhum manifest publicado"}
        />
        <ReleaseSummaryCard
          icon={ShieldCheck}
          label="Distribuicao"
          value={latest ? releaseSignatureLabel(latest.signature_status) : "-"}
          detail={latest?.signature_summary ?? "Aguardando release"}
          tone={latest?.signature_status === "signed" ? "ok" : latest?.signature_status === "mixed" ? "warn" : "neutral"}
        />
        <ReleaseSummaryCard
          icon={Download}
          label="Instaladores"
          value={`${latestInstallerCount.toLocaleString("pt-BR")} pronto(s)`}
          detail={latestReadyArtifacts.length > 0 ? latestReadyArtifacts.join(" | ") : "Sem EXE/MSI publicado"}
          tone={latestInstallerCount > 0 && latest?.checksums_url ? "ok" : "warn"}
        />
        <ReleaseSummaryCard
          icon={CalendarClock}
          label="Publicacao"
          value={formatDateTime(latest?.published_at ?? null)}
          detail={latest ? `Pacote total: ${formatBytes(latestTotalSize)}` : "Sem arquivos"}
        />
      </div>

      <Surface
        className={`mb-6 p-4 ${
          latest && latestInstallerCount > 0 && latest?.checksums_url
            ? "border-emerald-200 bg-emerald-50 text-emerald-900"
            : "border-amber-200 bg-amber-50 text-amber-900"
        }`}
      >
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="flex items-start gap-3">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-white/70">
              <PackageCheck className="h-5 w-5" />
            </div>
            <div>
              <h2 className="text-sm font-bold">
                {latest && latestInstallerCount > 0 && latest?.checksums_url ? "Release pronta para piloto interno" : "Release ainda incompleta"}
              </h2>
              <p className="mt-1 text-sm opacity-80">
                {latest && latestInstallerCount > 0 && latest?.checksums_url
                  ? `Versao ${latest.version} com ${latestReadyArtifacts.join(" + ")} publicada para instalacao em PCs de teste.`
                  : "Publique pelo menos um instalador e checksums SHA256 antes de instalar em campo."}
              </p>
              {latest?.signature_status !== "signed" ? (
                <p className="mt-2 text-xs font-semibold opacity-80">
                  Assinatura digital ainda pendente: para cliente externo, assine EXE/MSI com certificado de codigo.
                </p>
              ) : null}
            </div>
          </div>
          <Button variant="outline" onClick={load} disabled={loading} className="bg-white/70">
            <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
            Revalidar release
          </Button>
        </div>
      </Surface>

      {releaseIncomplete ? (
        <Surface className="mb-6 p-4">
          <div className="mb-4 flex items-start gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-md bg-primary/10 text-primary">
              <FileArchive className="h-5 w-5" />
            </div>
            <div>
              <h2 className="text-sm font-bold">Como publicar o instalador</h2>
              <p className="mt-1 max-w-3xl text-xs text-muted-foreground">
                Esta tela nao compila o EXE/MSI. Ela mostra e baixa as releases que ja foram geradas no Windows e publicadas na pasta
                <span className="mx-1 font-mono font-semibold text-foreground">agent/releases</span>
                da VPS. Depois que o manifest aparecer aqui, os comandos de instalacao silenciosa ficam prontos para copiar.
              </p>
            </div>
          </div>
          <div className="mb-4 rounded-md border border-blue-200 bg-blue-50 p-3 text-xs text-blue-900">
            <div className="font-bold">Fluxo correto</div>
            <div className="mt-1 text-blue-800">
              Gere a release no PC de desenvolvimento, publique a pasta <span className="font-mono">agent/releases</span> na VPS e clique em
              <span className="mx-1 font-semibold">Atualizar</span>
              nesta tela.
            </div>
          </div>
          <div className="grid gap-3 lg:grid-cols-3">
            <CommandBox
              title="1. Gerar no Windows"
              command={buildReleaseCommand}
              displayCommand={buildReleaseCommand}
              disabled={false}
              copied={copiedCommand === "build-release"}
              onCopy={() => copyCommand("build-release", buildReleaseCommand)}
            />
            <CommandBox
              title="2. Publicar na VPS"
              command={publishReleaseCommand}
              displayCommand={publishReleaseCommand}
              disabled={false}
              copied={copiedCommand === "publish-release"}
              onCopy={() => copyCommand("publish-release", publishReleaseCommand)}
            />
            <CommandBox
              title="3. Revalidar backend"
              command={reloadReleaseCommand}
              displayCommand={reloadReleaseCommand}
              disabled={false}
              copied={copiedCommand === "reload-release"}
              onCopy={() => copyCommand("reload-release", reloadReleaseCommand)}
            />
          </div>
        </Surface>
      ) : null}

      {isAdmin ? (
        <Surface className="mb-6 p-4">
          <div className="mb-4 flex flex-wrap items-start justify-between gap-4">
            <div className="flex items-start gap-3">
              <div className="flex h-9 w-9 items-center justify-center rounded-md bg-emerald-50 text-emerald-700">
                <ShieldCheck className="h-5 w-5" />
              </div>
              <div>
                <div className="flex flex-wrap items-center gap-2">
                  <h2 className="text-sm font-bold">Instalacao padrao para cliente</h2>
                  <span className="rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-xs font-bold text-emerald-700">
                    Recomendado
                  </span>
                </div>
                <p className="mt-1 max-w-3xl text-xs text-muted-foreground">
                  Envie o instalador padrao e uma chave de ativacao. O cliente nao precisa saber usuario, senha do agent ou slug da empresa.
                </p>
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button variant="outline" onClick={() => copyCommand("public-installer", publicInstallerUrl)} disabled={!installerFile}>
                {copiedCommand === "public-installer" ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                {copiedCommand === "public-installer" ? "Link copiado" : "Copiar link"}
              </Button>
              <Button onClick={() => window.open(publicInstallerUrl, "_blank")} disabled={!installerFile}>
                <Download className="h-4 w-4" />
                Baixar instalador
              </Button>
            </div>
          </div>

          <div className="mb-4 grid gap-3 md:grid-cols-[1.1fr_0.9fr]">
            <div className="rounded-md border bg-muted/20 p-3">
              <div className="mb-2 text-xs font-bold uppercase text-muted-foreground">Empresa de destino</div>
              {organizations.length > 0 ? (
                <select
                  className="h-10 w-full rounded-md border bg-white px-3 text-sm text-foreground outline-none focus-visible:border-primary focus-visible:ring-2 focus-visible:ring-ring/20"
                  value={deployOrg}
                  onChange={(event) => {
                    const slug = event.target.value;
                    if (slug !== deployOrg) {
                      setDeployPassword("");
                      setActivationKey("");
                    }
                    setDeployOrg(slug);
                    const organization = organizations.find((item) => item.slug === slug);
                    if (organization?.agent_username) setDeployUser(organization.agent_username);
                  }}
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
              <div className="mt-2 text-xs text-muted-foreground">
                {selectedOrganization?.enrollment_key_created_at
                  ? `Ultima chave gerada em ${formatDateTime(selectedOrganization.enrollment_key_created_at)}.`
                  : "Nenhuma chave de ativacao gerada para esta empresa nesta VPS."}
              </div>
            </div>
            <div className="rounded-md border bg-muted/20 p-3">
              <div className="mb-2 text-xs font-bold uppercase text-muted-foreground">Chave de ativacao</div>
              <div className="flex gap-2">
                <Input value={activationKey || "Gere uma chave para copiar"} readOnly className={activationKey ? "font-mono text-xs" : "text-muted-foreground"} />
                <Button variant="outline" className="shrink-0" onClick={rotateEnrollmentKey} disabled={generatingKey || !selectedOrganizationActive}>
                  <RefreshCw className={`h-4 w-4 ${generatingKey ? "animate-spin" : ""}`} />
                  Gerar
                </Button>
                <Button
                  variant="outline"
                  className="shrink-0"
                  onClick={() => copyCommand("activation-key", activationKey)}
                  disabled={!activationKey}
                  title="Copiar chave de ativacao"
                >
                  {copiedCommand === "activation-key" ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                </Button>
              </div>
              <div className="mt-2 text-xs text-muted-foreground">
                A chave pode ser rotacionada a qualquer momento. Chaves antigas param de ativar novas instalacoes.
              </div>
            </div>
          </div>

          <div className="grid gap-3 lg:grid-cols-2">
            <CommandBox
              title="Link do instalador padrao"
              command={publicInstallerUrl}
              displayCommand={publicInstallerUrl}
              disabled={!installerFile}
              copied={copiedCommand === "public-installer"}
              onCopy={() => copyCommand("public-installer", publicInstallerUrl)}
            />
            <CommandBox
              title="Comando silencioso com chave"
              command={activationCommand}
              displayCommand={activationCommand}
              disabled={!installerFile || !activationKey}
              emptyMessage={!installerFile ? "Publique o instalador antes de gerar o comando." : "Gere uma chave de ativacao para montar o comando."}
              copied={copiedCommand === "activation-command"}
              onCopy={() => copyCommand("activation-command", activationCommand)}
            />
          </div>
        </Surface>
      ) : null}

      {isAdmin ? (
        <Surface className="mb-6 p-4">
          <div className="mb-4 flex items-start gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-md bg-primary/10 text-primary">
              <TerminalSquare className="h-5 w-5" />
            </div>
            <div>
              <h2 className="text-sm font-bold">Instalacao silenciosa</h2>
              <p className="text-xs text-muted-foreground">Comandos PowerShell prontos para implantar o agent. A senha fica mascarada na tela, mas e copiada corretamente.</p>
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
                  onChange={(event) => {
                    const slug = event.target.value;
                    if (slug !== deployOrg) setDeployPassword("");
                    if (slug !== deployOrg) setActivationKey("");
                    setDeployOrg(slug);
                    const organization = organizations.find((item) => item.slug === slug);
                    if (organization?.agent_username) {
                      setDeployUser(organization.agent_username);
                    }
                  }}
                >
                  {organizations.map((organization) => (
                    <option key={organization.id} value={organization.slug} disabled={!organization.is_active}>
                      {organization.name} ({organization.slug}){organization.is_active ? billingStatusSuffix(organization.billing_status) : " - inativa"}
                    </option>
                  ))}
                </select>
              ) : (
                <Input
                  value={deployOrg}
                  onChange={(event) => {
                    if (event.target.value !== deployOrg) setDeployPassword("");
                    if (event.target.value !== deployOrg) setActivationKey("");
                    setDeployOrg(event.target.value);
                  }}
                />
              )}
            </label>
            <label className="grid gap-1.5 text-xs font-semibold text-muted-foreground">
              Usuario agent
              <Input
                value={deployUser}
                onChange={(event) => setDeployUser(event.target.value)}
                title={selectedOrganization?.agent_username ? `Usuario tecnico cadastrado: ${selectedOrganization.agent_username}` : undefined}
              />
            </label>
            <label className="grid gap-1.5 text-xs font-semibold text-muted-foreground">
              Senha atual do agent
              <Input type="password" value={deployPassword} onChange={(event) => setDeployPassword(event.target.value)} />
              <span className="text-[11px] font-medium text-muted-foreground">
                Use a senha cadastrada para o usuario tecnico desta empresa; ao trocar a empresa, este campo e limpo automaticamente.
              </span>
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
          <div className="mb-4 grid gap-3 md:grid-cols-4">
            <label className="grid gap-1.5 text-xs font-semibold text-muted-foreground">
              Comunidade SNMP
              <Input value={snmpCommunity} onChange={(event) => setSnmpCommunity(event.target.value)} />
            </label>
            <label className="grid gap-1.5 text-xs font-semibold text-muted-foreground">
              Coleta SNMP (s)
              <Input type="number" min={1} value={snmpPollInterval} onChange={(event) => setSnmpPollInterval(event.target.value)} />
            </label>
            <label className="grid gap-1.5 text-xs font-semibold text-muted-foreground">
              Timeout SNMP (s)
              <Input type="number" min={0.1} step={0.1} value={snmpTimeout} onChange={(event) => setSnmpTimeout(event.target.value)} />
            </label>
            <label className="grid gap-1.5 text-xs font-semibold text-muted-foreground">
              Tentativas SNMP
              <Input type="number" min={0} value={snmpRetries} onChange={(event) => setSnmpRetries(event.target.value)} />
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
          <div className="mb-4 rounded-md border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900">
            <div className="flex items-start gap-2">
              <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0" />
              <div>
                <div className="font-bold">Execute o comando em PowerShell como Administrador.</div>
                <div className="mt-0.5 text-amber-800">
                  Sem elevacao, o agent pode instalar parcialmente e aparecer em Agents como &quot;Sem admin local&quot;, limitando criacao/restauracao de filas e acoes remotas.
                </div>
              </div>
            </div>
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
                        {release.checksums_sha256 ? (
                          <div className="mt-2 flex max-w-[220px] items-center gap-2">
                            <span className="truncate font-mono text-[11px] text-muted-foreground" title={release.checksums_sha256}>
                              {release.checksums_sha256}
                            </span>
                            <Button
                              variant="outline"
                              className="h-7 shrink-0 px-2 text-xs"
                              onClick={() => copyChecksumsSha(release)}
                              title="Copiar SHA256 do SHA256SUMS"
                            >
                              {copiedSha === `${release.version}:SHA256SUMS` ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
                            </Button>
                          </div>
                        ) : null}
                      </td>
                      <td className="p-4">
                        <div className="flex items-center gap-2 font-medium">
                          <FileArchive className="h-4 w-4 text-primary" />
                          {file.filename}
                        </div>
                        {release.notes ? <div className="mt-1 text-xs text-muted-foreground">{release.notes}</div> : null}
                      </td>
                      <td className="p-4">
                        <span
                          className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-semibold ${artifactKindClass(file.kind, file.filename)}`}
                          title={file.kind}
                        >
                          <ShieldCheck className="h-3 w-3" />
                          {artifactKindLabel(file.kind, file.filename)}
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
                          <Button variant="outline" className="h-7 shrink-0 px-2 text-xs" onClick={() => copySha(file, release.version)} title="Copiar SHA256">
                            {copiedSha === `${release.version}:${file.filename}` ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
                            {copiedSha === `${release.version}:${file.filename}` ? "Copiado" : "Copiar"}
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

function ReleaseSummaryCard({
  icon: Icon,
  label,
  value,
  detail,
  tone = "neutral",
}: {
  icon: ComponentType<{ className?: string }>;
  label: string;
  value: string;
  detail: string;
  tone?: "neutral" | "ok" | "warn";
}) {
  const toneClass =
    tone === "ok"
      ? "border-emerald-200 bg-emerald-50 text-emerald-700"
      : tone === "warn"
      ? "border-amber-200 bg-amber-50 text-amber-700"
      : "border-slate-200 bg-slate-100 text-slate-700";

  return (
    <Surface className="p-4">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div className="text-xs font-semibold uppercase text-muted-foreground">{label}</div>
        <span className={`flex h-8 w-8 items-center justify-center rounded-md border ${toneClass}`}>
          <Icon className="h-4 w-4" />
        </span>
      </div>
      <div className="text-xl font-bold">{value}</div>
      <div className="mt-1 line-clamp-2 text-xs text-muted-foreground" title={detail}>
        {detail}
      </div>
    </Surface>
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
