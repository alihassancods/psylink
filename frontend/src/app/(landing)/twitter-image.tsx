import { ImageResponse } from "next/og";

import { OgImageCard } from "@/components/landing/og-image-card";
import { product } from "@/app/(landing)/content";

/**
 * Twitter/X reads `twitter:image` rather than falling back to `og:image`, so this renders the same
 * shared card. The duplication is the two metadata exports Next requires, not the artwork.
 */
export const alt = `${product.name}: ${product.tagline}. A one-minute voice check-in that helps a visit start with a clearer picture. Not emergency care; demo data is synthetic.`;
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

export default function TwitterImage() {
  return new ImageResponse(<OgImageCard />, size);
}
