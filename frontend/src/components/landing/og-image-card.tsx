import { hero, product } from "@/app/(landing)/content";

/**
 * The social card for the landing page, shared by `opengraph-image.tsx` and `twitter-image.tsx` so
 * the two can never render differently.
 *
 * Constraints worth knowing before editing: Satori lays out with flexbox only — no `display: grid`,
 * no Tailwind classes, every value explicit — and it renders the tree to PNG at build time. The copy
 * comes from content.ts, so changing the tagline changes this card too.
 *
 * Deliberately plain: no robot, no glowing brain. A mental-health product introducing itself should
 * look like a clinic's waiting room, not a launch page, and the limits are stated on the card itself
 * because a shared preview is often the only thing a first-time reader sees.
 */

const SLATE_50 = "#f8fafc";
const SLATE_900 = "#0f172a";
const SLATE_600 = "#475569";
const SLATE_200 = "#e2e8f0";
const TEAL_700 = "#0f766e";
const TEAL_600 = "#0d9488";

/** Fourteen synthetic days — the same dip-and-recover shape as the hero mock. */
const LINE = [48, 53, 58, 62, 67, 77, 82, 77, 72, 67, 58, 53, 48, 44];

/** Chart box. Values are mood scores where a larger number means a worse day, i.e. lower down. */
const CHART_W = 360;
const CHART_H = 220;
const PAD_X = 12;
const PAD_Y = 40;

export function OgImageCard() {
  const lowest = Math.min(...LINE);
  const highest = Math.max(...LINE);
  const points = LINE.map((value, index) => {
    const x = PAD_X + index * ((CHART_W - PAD_X * 2) / (LINE.length - 1));
    const y = PAD_Y + ((value - lowest) / (highest - lowest)) * (CHART_H - PAD_Y * 2);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");

  return (
    <div
      style={{
        display: "flex",
        width: "100%",
        height: "100%",
        padding: "72px 80px",
        backgroundColor: SLATE_50,
        backgroundImage: `linear-gradient(135deg, ${SLATE_50} 0%, #ffffff 60%)`,
        fontFamily: "sans-serif",
      }}
    >
      <div style={{ display: "flex", flexDirection: "column", justifyContent: "space-between", flex: "1 1 0%" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "16px" }}>
          <div
            style={{
              display: "flex",
              width: "44px",
              height: "44px",
              borderRadius: "14px",
              backgroundColor: TEAL_700,
            }}
          />
          <div style={{ display: "flex", fontSize: "34px", fontWeight: 600, color: SLATE_900 }}>
            {product.name}
          </div>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: "20px" }}>
          <div
            style={{
              display: "flex",
              fontSize: "76px",
              fontWeight: 700,
              lineHeight: 1.1,
              color: SLATE_900,
              letterSpacing: "-1.5px",
            }}
          >
            {hero.heading}
          </div>
          <div style={{ display: "flex", fontSize: "32px", color: SLATE_600, lineHeight: 1.35 }}>
            Record a one-minute check-in. Your psychologist or psychiatrist sees how your week went
            before your next visit.
          </div>
        </div>

        <div style={{ display: "flex", fontSize: "24px", color: SLATE_600, marginTop: "28px" }}>
          {hero.notice}
        </div>
      </div>

      {/* The trend, in a card — the product's one visible artefact, drawn not photographed. */}
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          width: "420px",
          marginLeft: "64px",
          padding: "28px",
          borderRadius: "24px",
          backgroundColor: "#ffffff",
          border: `1px solid ${SLATE_200}`,
          boxShadow: "0 12px 32px rgba(15, 23, 42, 0.06)",
        }}
      >
        <div style={{ display: "flex", fontSize: "22px", fontWeight: 600, color: SLATE_900 }}>
          Mood over 14 days
        </div>
        <div style={{ display: "flex", fontSize: "18px", color: SLATE_600, marginTop: "4px" }}>
          Demo data
        </div>
        <svg
          width={CHART_W}
          height={CHART_H}
          viewBox={`0 0 ${CHART_W} ${CHART_H}`}
          style={{ display: "flex", marginTop: "20px" }}
        >
          <line x1="0" y1={CHART_H - 10} x2={CHART_W} y2={CHART_H - 10} stroke={SLATE_200} strokeWidth="1" />
          <line x1="0" y1="110" x2={CHART_W} y2="110" stroke={SLATE_200} strokeWidth="1" />
          <line x1="0" y1="40" x2={CHART_W} y2="40" stroke={SLATE_200} strokeWidth="1" />
          <polyline
            points={points}
            fill="none"
            stroke={TEAL_600}
            strokeWidth="5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </div>
    </div>
  );
}
