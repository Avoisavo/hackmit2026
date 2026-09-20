import type { Metadata } from "next";
import BuddyAgent from "./BuddyAgent";

export const metadata: Metadata = {
  title: "Talk with Buddy",
};

export default function DeepgramPage() {
  return (
    <main className="min-h-screen px-6 py-16">
      <BuddyAgent />
    </main>
  );
}
