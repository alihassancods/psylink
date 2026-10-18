import { ImageResponse } from "next/og";

import { OgImageCard } from "@/components/landing/og-image-card";
import { product } from "@/app/(landing)/content";

/**
 * Open Graph preview for `/`. Next links this automatically as `og:image` for the segment.
 * `size` stays a literal here rather than an imported constant — these metadata exports are read
 * statically at build time.
 */
export const alt = `${product.name}: ${product.tagline}. A one-minute voice check-in that helps a visit start with a clearer picture. Not emergency care; demo data is synthetic.`;
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

export default function OpengraphImage() {
  return new ImageResponse(<OgImageCard />, size);
}
