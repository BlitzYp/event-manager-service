import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Event Manager",
  description: "Independent event wallet and coupon management",
  robots: { index: false, follow: false },
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
