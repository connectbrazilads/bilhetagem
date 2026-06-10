"use client";

import { useEffect, useState } from "react";
import { Download, FileArchive, RefreshCw, ShieldCheck } from "lucide-react";

import { ProtectedPage } from "@/components/protected-page";
import { Button, Surface } from "@/components/ui";
import { API_URL, apiFetch } from "@/lib/api";

type ReleaseFile = {
  kind: string;
  filename: string;
  size_bytes: number;
  sha256: string;
  download_url: string;
};

type AgentRelease = {
  version: string;
  channel: string;
  published_at: string | null;
  notes: string | null;
  files: ReleaseFile[];
};

function formatBytes(value: number) {
  if (value > 1024 * 1024) return `${(value / 1024 / 1024).toFixed(1)} MB`;
  if (value > 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${value} B`;
}

export default function DownloadsPage() {
  const [releases, setReleases] = useState<AgentRelease[]>([]);
  const [loading, setLoading] = useState(false);

  async function load() {
    const token = localStorage.getItem("token");
    if (!token) return;
    setLoading(true);
    try {
      const data = await apiFetch<AgentRelease[]>("/agent/releases", token);
      setReleases(data);
    } catch {
      setReleases([]);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function downloadFile(file: ReleaseFile) {
    const token = localStorage.getItem("token");
    if (!token) return;
    const response = await fetch(`${API_URL}${file.download_url}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = file.filename;
    link.click();
    URL.revokeObjectURL(url);
  }

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
                      <td className="p-4 text-right">{formatBytes(file.size_bytes)}</td>
                      <td className="max-w-[340px] truncate p-4 font-mono text-xs" title={file.sha256}>
                        {file.sha256}
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
