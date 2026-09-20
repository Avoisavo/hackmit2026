/**
 * Robot voice. speak() resolves when PLAYBACK FINISHES, not when the request
 * returns — that promise is the hinge the whole turn-taking loop swings on.
 *
 * Provider is swappable: /api/tts?provider=elevenlabs|deepgram. Both stream
 * mp3 progressively, so an <audio> element plays them with no MediaSource code
 * and still fires `ended`.
 */

export type TtsProvider = "elevenlabs" | "deepgram";

export class RobotVoice {
  private audio: HTMLAudioElement | null = null;
  private unlocked = false;

  constructor(private provider: TtsProvider = "elevenlabs") {}

  setProvider(p: TtsProvider) { this.provider = p; }

  /**
   * Browsers reject programmatic play() outside a user gesture. Call this once
   * from the Start button click, then the robot can talk for the rest of the
   * session.
   */
  unlock() {
    if (this.unlocked) return;
    const a = new Audio();
    a.src = "data:audio/mpeg;base64,SUQzBAAAAAAAI1RTU0UAAAAPAAADTGF2ZjYwLjE2LjEwMQAAAAAAAAAAAAAA";
    a.volume = 0;
    a.play().catch(() => {});
    this.audio = a;
    this.unlocked = true;
  }

  /** Speak `text`, resolving once the audio has finished playing. */
  speak(text: string): Promise<void> {
    this.cancel();

    return new Promise<void>((resolve) => {
      const url = `/api/tts?provider=${this.provider}&text=${encodeURIComponent(text)}`;
      const audio = new Audio(url);
      audio.preload = "auto";
      this.audio = audio;

      const finish = () => {
        audio.removeEventListener("ended", finish);
        audio.removeEventListener("error", finish);
        if (this.audio === audio) this.audio = null;
        resolve();
      };

      // Resolve on error too — a failed line must not deadlock the game.
      audio.addEventListener("ended", finish, { once: true });
      audio.addEventListener("error", finish, { once: true });

      audio.play().catch(finish);
    });
  }

  /**
   * Stop playback AND abort the in-flight request. Pausing alone leaves the
   * HTTP request running and you keep paying for audio nobody hears.
   */
  cancel() {
    const a = this.audio;
    if (!a) return;
    a.pause();
    a.removeAttribute("src");
    a.load();
    this.audio = null;
  }
}
