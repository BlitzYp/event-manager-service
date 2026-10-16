import type { Metadata } from "next";
import { Analytics } from "@vercel/analytics/next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Event Manager",
  description: "Independent event wallet and coupon management",
  robots: { index: false, follow: false },
};

/** Provide the shared page shell, fonts, metadata, and analytics for every route. */
export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        {children}
        <Analytics />
      </body>
    </html>
  );
}
