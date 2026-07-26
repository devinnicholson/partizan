import type { Metadata, Viewport } from "next";
import { headers } from "next/headers";
import "./globals.css";

const title = "Partizan — One Value, Three Forms";
const description =
  "Three certified realizations cross graph and game structure while exact combinatorial-game value remains fixed.";

export async function generateMetadata(): Promise<Metadata> {
  const requestHeaders = await headers();
  const host =
    requestHeaders.get("x-forwarded-host") ??
    requestHeaders.get("host") ??
    "localhost:4173";
  const protocol =
    requestHeaders.get("x-forwarded-proto") ??
    (host.startsWith("localhost") ? "http" : "https");
  const origin = new URL(`${protocol}://${host}`);
  const socialImage = new URL("/og.png", origin).toString();

  return {
    metadataBase: origin,
    title,
    description,
    icons: {
      icon: "/favicon.png",
      shortcut: "/favicon.png",
    },
    openGraph: {
      title,
      description,
      type: "website",
      images: [{ url: socialImage, width: 1536, height: 1024, alt: title }],
    },
    twitter: {
      card: "summary_large_image",
      title,
      description,
      images: [socialImage],
    },
  };
}

export const viewport: Viewport = {
  colorScheme: "dark",
  themeColor: "#070807",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
