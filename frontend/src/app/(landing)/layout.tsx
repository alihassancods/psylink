import type { Metadata } from "next";

import { product } from "@/app/(landing)/content";
import { SITE_URL } from "@/lib/env";

export const metadata: Metadata = {
  title: `${product.name}: ${product.tagline}`,
  description:
    "Record a one-minute check-in. Your psychologist or psychiatrist sees how your week went before your next visit. Not emergency care; demo data is synthetic.",
  metadataBase: new URL(SITE_URL),
  openGraph: {
    type: "website",
    url: "/",
    siteName: product.name,
    title: `${product.name}: ${product.tagline}`,
    description:
      "A one-minute voice check-in that helps your visit start with a clearer picture. Not a diagnosis, not emergency care.",
  },
  twitter: {
    card: "summary_large_image",
    title: `${product.name}: ${product.tagline}`,
    description: "Record a one-minute check-in. Your provider sees how your week went.",
  },
};

/**
 * The landing page is the public face of the product, so it deliberately carries no app shell: the
 * patient and provider chrome belongs to the signed-in route groups, not to a visitor deciding
 * whether to try the demo.
 */
export default function LandingLayout({ children }: { children: React.ReactNode }) {
  return <div className="flex flex-1 flex-col">{children}</div>;
}
