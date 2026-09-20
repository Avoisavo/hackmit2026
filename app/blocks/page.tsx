import type { Metadata } from "next";
import BlockGame from "./BlockGame";

export const metadata: Metadata = {
  title: "Block counting game",
};

export default function BlocksPage() {
  return (
    <main className="min-h-screen px-6 py-12">
      <BlockGame />
    </main>
  );
}
