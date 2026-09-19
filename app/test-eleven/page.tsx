import VoiceTutor from "./VoiceTutor";

export const metadata = {
  title: "Talk with Buddy",
  description: "A voice practice buddy that helps kids name their feelings.",
};

export default function TestElevenPage() {
  return (
    <div className="flex flex-1 flex-col items-center justify-center bg-gradient-to-b from-sky-50 to-white px-6 py-16 dark:from-slate-900 dark:to-black">
      <h1 className="mb-10 text-center text-4xl font-bold tracking-tight text-slate-800 dark:text-slate-100">
        Talk with Buddy
      </h1>
      <VoiceTutor />
    </div>
  );
}
