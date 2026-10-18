import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  cacheComponents: true,
  partialPrefetching: true,
  // Tailwind v4 runs through `@tailwindcss/postcss` (see postcss.config.mjs) in Turbopack's native
  // PostCSS worker pool. A `turbopack.rules` loader for `*.css` is the wrong path here: Turbopack
  // needs no loader config for built-ins and does not support loaders that transform stylesheets,
  // and the loader's `base` defaulted to the whole project directory — node_modules included.
  experimental: {
    // Dev only. Defers compiling the lazily-loaded chart chunks until the browser asks for them.
    turbopackLazyDynamicImports: true,
    /**
     * Every page in this app sits behind a client-side Supabase session check, so no page can render
     * during prerender and the default per-page validation flags all ten of them as "dropped
     * segments" on every dev load and HMR update — noise that hides the cases worth seeing.
     * `manual-warning` validates only segments that opt in with an explicit `instant`, which is the
     * documented setting for this shape.
     * (instant.md: "Only segments with an explicit `instant` are validated").
     */
    instantInsights: {
      validationLevel: "manual-warning",
    },
  },
};

export default nextConfig;
