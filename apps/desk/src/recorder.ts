/** Browser-side meeting recorder: 16 kHz mono PCM, WAV chunks every N seconds, uploaded with a checksum.
 *  Needs a secure context (HTTPS or localhost). The desk Pi should use companion-audio instead. */
import { api } from "./api";

export function encodeWav(samples: Int16Array, sampleRate = 16000): Blob {
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const v = new DataView(buffer);
  const w = (o: number, s: string) => { for (let i = 0; i < s.length; i++) v.setUint8(o + i, s.charCodeAt(i)); };
  w(0, "RIFF"); v.setUint32(4, 36 + samples.length * 2, true); w(8, "WAVE"); w(12, "fmt ");
  v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true); v.setUint32(24, sampleRate, true);
  v.setUint32(28, sampleRate * 2, true); v.setUint16(32, 2, true); v.setUint16(34, 16, true); w(36, "data"); v.setUint32(40, samples.length * 2, true);
  new Int16Array(buffer, 44).set(samples);
  return new Blob([buffer], { type: "audio/wav" });
}

async function sha256Hex(blob: Blob): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", await blob.arrayBuffer());
  return Array.from(new Uint8Array(digest)).map((b) => b.toString(16).padStart(2, "0")).join("");
}

export class MeetingRecorder {
  private ctx: AudioContext | null = null;
  private stream: MediaStream | null = null;
  private node: ScriptProcessorNode | null = null;
  private buf: number[] = [];
  private seq = 0;
  private timer: number | undefined;
  private paused = false;
  public uploaded = 0;
  public lastError: string | null = null;

  constructor(private recordingId: string, private chunkSeconds = 20, private onChunk?: (seq: number) => void) {}

  static supported(): boolean { return typeof window !== "undefined" && window.isSecureContext && !!navigator.mediaDevices?.getUserMedia; }

  async start(): Promise<void> {
    this.stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true } });
    this.ctx = new AudioContext();
    const src = this.ctx.createMediaStreamSource(this.stream);
    this.node = this.ctx.createScriptProcessor(4096, 1, 1);
    const ratio = this.ctx.sampleRate / 16000;
    this.node.onaudioprocess = (e) => {
      if (this.paused) return;
      const input = e.inputBuffer.getChannelData(0);
      for (let i = 0; i < input.length; i += ratio) { // simple decimation to 16 kHz
        const s = Math.max(-1, Math.min(1, input[Math.floor(i)]));
        this.buf.push(s < 0 ? s * 0x8000 : s * 0x7fff);
      }
    };
    src.connect(this.node); this.node.connect(this.ctx.destination);
    this.timer = window.setInterval(() => void this.flush(), this.chunkSeconds * 1000);
  }

  pause() { this.paused = true; }
  resume() { this.paused = false; }

  private async flush(): Promise<void> {
    if (this.buf.length < 1600) return; // < 0.1 s: nothing worth sending
    const samples = Int16Array.from(this.buf); this.buf = [];
    const wav = encodeWav(samples);
    const seq = this.seq++;
    try { await api.putChunk(this.recordingId, seq, wav, await sha256Hex(wav)); this.uploaded++; this.onChunk?.(seq); }
    catch (e) { this.lastError = (e as Error).message; }
  }

  async stop(): Promise<void> {
    if (this.timer) window.clearInterval(this.timer);
    await this.flush();
    this.node?.disconnect(); this.stream?.getTracks().forEach((t) => t.stop()); await this.ctx?.close();
    this.node = null; this.stream = null; this.ctx = null;
  }
}
