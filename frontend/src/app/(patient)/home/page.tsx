import type { Metadata } from "next";

import { HomeView } from "@/components/patient/home-view";

export const metadata: Metadata = { title: "Psylink" };

export default function HomePage() {
  return <HomeView />;
}
