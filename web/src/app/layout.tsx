import type { Metadata } from "next";
import { Inter } from "next/font/google";

import { TopBar } from "../components/TopBar";
import { Providers } from "../lib/providers";
import { themeInitScript } from "../lib/theme";
import "./globals.css";
import "./kit.css";

const inter = Inter({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700", "800"],
  variable: "--font-inter",
});

export const metadata: Metadata = {
  title: "Oikonomos",
  description: "An AI operator that holds, splits and grows a small business's USDC on Arc.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={inter.variable} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeInitScript }} />
      </head>
      <body>
        <Providers>
          <TopBar />
          <main>{children}</main>
        </Providers>
      </body>
    </html>
  );
}
