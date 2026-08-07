import type { Metadata, Viewport } from "next";
import { headers } from "next/headers";
import "./globals.css";

const title = "Partizan | A Fixed-Value Atlas";
const description =
  "An interactive atlas of 21,697 certified order-7 Digraph Placement graphs, grouped into 16,120 complete games and three exact values.";

function normalizedBasePath() {
  const value = process.env.NEXT_PUBLIC_PARTIZAN_BASE_PATH ?? "";
  if (!value || value === "/") return "";
  return `/${value.replace(/^\/+|\/+$/g, "")}`;
}

export async function generateMetadata(): Promise<Metadata> {
  const requestHeaders = await headers();
  const host =
    requestHeaders.get("x-forwarded-host") ??
    requestHeaders.get("host") ??
    "localhost:4173";
  const protocol =
    requestHeaders.get("x-forwarded-proto") ??
    (host.startsWith("localhost") ? "http" : "https");
  const configuredOrigin = process.env.PARTIZAN_PUBLIC_ORIGIN;
  const origin = new URL(configuredOrigin ?? `${protocol}://${host}`);
  const basePath = normalizedBasePath();
  const socialImage = new URL(`${basePath}/og.png`, origin).toString();
  const favicon = new URL(`${basePath}/favicon.png`, origin).toString();

  return {
    metadataBase: origin,
    title,
    description,
    icons: {
      icon: favicon,
      shortcut: favicon,
    },
    openGraph: {
      title,
      description,
      type: "website",
      images: [
        {
          url: socialImage,
          width: 1536,
          height: 1024,
          alt: "Graph forms grouped by complete-game identity and exact value in the Partizan fixed-value atlas.",
        },
      ],
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
  themeColor: "#090908",
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
