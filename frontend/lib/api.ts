export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type DashboardMetrics = {
  prints_today: number;
  prints_month: number;
  pages_today: number;
  pages_month: number;
  top_users: { username: string; pages: number }[];
  top_printers: { printer: string; pages: number }[];
  department_usage: { department: string; pages: number }[];
  color_usage: { type: string; pages: number }[];
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
        localStorage.removeItem("token");
        window.location.href = "/";
      }
    }
    const detail = await response.text();
    throw new Error(detail || `Erro ${response.status}`);
  }
  return response.json() as Promise<T>;
}
