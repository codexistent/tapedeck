import type { Metadata } from "next";
import type { ReactNode } from "react";

import "./globals.css";

export const metadata: Metadata = {
  title: { default: "Tapedeck", template: "%s · Tapedeck" },
  description:
    "Regression tests for AI agents. Replay changed agents against recorded runs and fail pull requests only on statistically real regressions.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
