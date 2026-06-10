export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type DashboardMetrics = {
  prints_today: number;
  prints_month: number;
  pages_today: number;
  pages_month: number;
  contract_overview?: {
    billing_plan: string;
    billing_status: "trial" | "active" | "past_due" | "suspended";
    contracted_printer_limit: number;
    active_printers_count: number;
    printer_usage_percent: number;
    printer_limit_status: "unlimited" | "ok" | "warning" | "exceeded";
  } | null;
  operational_health?: {
    agents_total: number;
    agents_online: number;
    agents_offline: number;
    agents_with_alerts: number;
    agents_without_local_admin: number;
    agents_without_event_log: number;
    outdated_agents: number;
    printers_total: number;
    printers_monitored: number;
    printers_unmonitored: number;
    low_toner_printers: number;
    unbound_queues: number;
    usb_queues: number;
    duplicate_queue_aliases: number;
    generic_queue_aliases: number;
    hardware_identity_conflicts: number;
    pending_queue_actions: number;
    stale_queue_actions: number;
  } | null;
  top_users: { username: string; pages: number; cost?: number; cost_per_page?: number }[];
  top_printers: { printer: string; pages: number; cost?: number; cost_per_page?: number }[];
  department_usage: { department: string; pages: number; cost?: number; cost_per_page?: number }[];
  color_usage: { type: string; pages: number; cost?: number; cost_per_page?: number }[];
  eco_metrics?: {
    pages_saved: number;
    co2_saved_g: number;
    water_saved_l: number;
    trees_saved: number;
  };
};

export function isTokenExpired(token: string): boolean {
  try {
    const parts = token.split(".");
    if (parts.length !== 3) return true;
    const payload = JSON.parse(atob(parts[1].replace(/-/g, "+").replace(/_/g, "/")));
    if (typeof payload.exp !== "number") return false;
    const now = Math.floor(Date.now() / 1000);
    return payload.exp < now;
  } catch {
    return true;
  }
}

export function getCurrentUsername(token: string): string | null {
  try {
    const parts = token.split(".");
    if (parts.length !== 3) return null;
    const payload = JSON.parse(atob(parts[1].replace(/-/g, "+").replace(/_/g, "/")));
    return payload.sub || null;
  } catch {
    return null;
  }
}

export function getCurrentRole(token: string): string | null {
  try {
    const parts = token.split(".");
    if (parts.length !== 3) return null;
    const payload = JSON.parse(atob(parts[1].replace(/-/g, "+").replace(/_/g, "/")));
    return payload.role || null;
  } catch {
    return null;
  }
}

export function clearAuthStorage() {
  localStorage.removeItem("token");
  localStorage.removeItem("organization_slug");
  localStorage.removeItem("organization_name");
  localStorage.removeItem("organization_billing_status");
}

export async function apiFetch<T>(path: string, token: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
      ...(init?.headers ?? {})
    }
  });

  if (!response.ok) {
    if (response.status === 401) {
      if (typeof window !== "undefined") {
        clearAuthStorage();
        window.location.href = "/";
      }
    }
    const detail = await response.text();
    throw new Error(detail || `Erro ${response.status}`);
  }
  return response.json() as Promise<T>;
}
