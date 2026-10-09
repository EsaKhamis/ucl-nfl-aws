import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "NFL TOE Broadcast Dashboard",
  description:
    "Target Over Expectation analytics for broadcasters, commentators, and analysts.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-ink text-slate-100 antialiased">
        {children}
      </body>
    </html>
  );
}
