import type { Metadata, Viewport } from "next";
import { Aref_Ruqaa, Geist_Mono, Readex_Pro } from "next/font/google";
import "./globals.css";
import { AuthProvider } from "@/auth/auth-provider";
import { GlobalNavbar } from "@/components/layout/GlobalNavbar";
import { GlobalFooter } from "@/components/layout/GlobalFooter";

const readex = Readex_Pro({
  variable: "--font-readex",
  subsets: ["arabic", "latin"],
});

const aref = Aref_Ruqaa({
  variable: "--font-aref-ruqaa",
  subsets: ["arabic", "latin"],
  weight: ["400", "700"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "مرشدي | Morshidi — بوابتك الأكاديمية",
  description: "خطتك وسجلك ومسارك الدراسي في مكان واحد.",
  icons: {
    icon: [
      { url: "/favicon.ico" },
      { url: "/favicon.ico", sizes: "any" },
    ],
    shortcut: "/favicon.ico",
    apple: "/brand/morshidi-guide.png",
  },
};

export const viewport: Viewport = { themeColor: "#0B1210", width: "device-width", initialScale: 1 };

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html
      lang="ar"
      dir="rtl"
      suppressHydrationWarning
      className={`${readex.variable} ${aref.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col bg-[#0B1210] text-[#F3E9D8]">
        <AuthProvider>
          <GlobalNavbar />
          <main className="flex-1">{children}</main>
          <GlobalFooter />
        </AuthProvider>
      </body>
    </html>
  );
}
