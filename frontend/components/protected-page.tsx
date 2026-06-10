"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { AppShell } from "@/components/shell";
import { clearAuthStorage, getCurrentRole, isTokenExpired } from "@/lib/api";

type ProtectedPageProps = {
  children: React.ReactNode;
  roles?: string[];
};

const DEFAULT_PANEL_ROLES = ["admin", "manager"];

export function ProtectedPage({ children, roles }: ProtectedPageProps) {
  const router = useRouter();
  const [ready, setReady] = useState(false);
  const allowedRoles = roles ?? DEFAULT_PANEL_ROLES;
  const allowedRolesKey = allowedRoles.join(",");

  useEffect(() => {
    const token = localStorage.getItem("token");
    if (!token || isTokenExpired(token)) {
      clearAuthStorage();
      router.replace("/");
      return;
    }
    const role = getCurrentRole(token);
    if (!role || role === "agent") {
      clearAuthStorage();
      router.replace("/");
      return;
    }
    if (!allowedRoles.includes(role)) {
      if (role === "manager") {
        router.replace("/dashboard");
      } else {
        clearAuthStorage();
        router.replace("/");
      }
      return;
    }
    setReady(true);
  }, [router, allowedRolesKey]);

  if (!ready) {
    return <div className="flex min-h-screen items-center justify-center text-sm text-muted-foreground">Carregando...</div>;
  }

  return <AppShell>{children}</AppShell>;
}
