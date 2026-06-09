"use client";

import { useEffect, useState } from "react";

import { ProtectedPage } from "@/components/protected-page";
import { Surface } from "@/components/ui";
import { apiFetch } from "@/lib/api";

type QuotaRow = {
  id: number;
  username: string;
  year: number;
  month: number;
  monthly_limit: number;
  used_pages: number;
  remaining_pages: number;
};

export default function QuotasPage() {
  const [quotas, setQuotas] = useState<QuotaRow[]>([]);

  useEffect(() => {
    const token = localStorage.getItem("token");
    if (token) apiFetch<QuotaRow[]>("/quotas", token).then(setQuotas).catch(() => setQuotas([]));
  }, []);

  return (
    <ProtectedPage>
      <h1 className="mb-5 text-xl font-semibold">Controle de cotas</h1>
      <Surface className="overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-muted text-left">
            <tr>
              <th className="p-3">Usuario</th>
              <th className="p-3">Periodo</th>
              <th className="p-3">Limite</th>
              <th className="p-3">Utilizado</th>
              <th className="p-3">Saldo</th>
            </tr>
          </thead>
          <tbody>
            {quotas.map((quota) => (
              <tr key={quota.id} className="border-t">
                <td className="p-3 font-medium">{quota.username}</td>
                <td className="p-3">
                  {quota.month}/{quota.year}
                </td>
                <td className="p-3">{quota.monthly_limit}</td>
                <td className="p-3">{quota.used_pages}</td>
                <td className="p-3">{quota.remaining_pages}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Surface>
    </ProtectedPage>
  );
}
