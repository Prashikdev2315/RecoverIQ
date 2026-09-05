import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AI Revenue Recovery Agent",
  description: "Razorpay Buildathon - Track 03",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="min-h-full bg-gray-50">{children}</body>
    </html>
  );
}
