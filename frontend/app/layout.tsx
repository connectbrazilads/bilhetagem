import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "PrintBilling",
  description: "Sistema de bilhetagem e controle de cotas de impressao"
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="pt-BR">
      <body>{children}</body>
    </html>
  );
}
