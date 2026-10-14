import type { Metadata } from "next";
import { SWRConfig } from "swr";
import "./globals.css";
import "./tech.css";

export const metadata: Metadata = {
  title: "Skillmentor — Interview practice",
  description: "A focused workspace for improving your interview answers and coding practice.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body><SWRConfig value={{ revalidateOnFocus: false, dedupingInterval: 3000 }}>{children}</SWRConfig></body></html>;
}
