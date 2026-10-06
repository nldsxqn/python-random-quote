import type { Metadata } from "next";
import type { ReactNode } from "react";

import { LanguageProvider } from "@/lib/i18n";

import "./globals.css";

export const metadata: Metadata = {
  title: "OpenPokerLab",
  description: "Self-hosted NLHE cash-game lab for entertainment, research, and training.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="zh-CN">
      <body>
        <LanguageProvider>{children}</LanguageProvider>
      </body>
    </html>
  );
}
