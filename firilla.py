"""Voice-lock engine: hears "Firilla lock", verifies the speaker, locks Windows."""
import ctypes
import difflib
import json
import queue
import re
import subprocess
import threading
import time
from pathlib import Path

import numpy as np
import sounddevice as sd

SR = 16000
BLOCK = int(SR * 0.03)
HERE = Path(__file__).parent
VOICEPRINT = HERE / "voiceprint.npy"
CONFIG = HERE / "config.json"
PHRASE = "Firilla lock"
DEFAULTS = {"device": None, "threshold": 0.75, "test_mode": False}


MODELS = HERE / "models"
WHISPER_DIR = MODELS / "base.en"          # lives next to the app so the folder is portable
WHISPER_REPO = "Systran/faster-whisper-base.en"
WHISPER_BYTES = 145_000_000               # approx size, for the progress bar
_download_lock = threading.Lock()


def whisper_ready():
    return (WHISPER_DIR / "model.bin").exists()


def download_whisper(progress=None):
    """Fetch the speech model into ./models (one time). progress(done, total) gets byte counts;
    with no callback the usual console progress bars are shown."""
    with _download_lock:
        if whisper_ready():
            return
        import os
        from huggingface_hub import snapshot_download
        kwargs = dict(repo_id=WHISPER_REPO, local_dir=str(WHISPER_DIR),
                      allow_patterns=["config.json", "preprocessor_config.json", "model.bin",
                                      "tokenizer.json", "vocabulary.*"])
        if progress is not None:
            from tqdm import tqdm
            done = [0]

            class Bar(tqdm):
                def __init__(self, *a, **k):
                    k["file"] = open(os.devnull, "w")
                    k.pop("name", None)
                    super().__init__(*a, **k)

                def update(self, n=1):
                    r = super().update(n)
                    if self.unit == "B":
                        done[0] += n or 0
                        progress(min(done[0], WHISPER_BYTES), WHISPER_BYTES)
                    return r
            kwargs["tqdm_class"] = Bar
        snapshot_download(**kwargs)


def load_config():
    try:
        return {**DEFAULTS, **json.loads(CONFIG.read_text())}
    except (OSError, ValueError):
        return dict(DEFAULTS)


def save_config(cfg):
    CONFIG.write_text(json.dumps(cfg, indent=2))


def input_devices():
    """[(index, name)] of microphones, MME host API only (avoids duplicates)."""
    apis = sd.query_hostapis()
    mme = next((i for i, a in enumerate(apis) if "MME" in a["name"]), None)
    return [(i, d["name"]) for i, d in enumerate(sd.query_devices())
            if d["max_input_channels"] > 0 and d["hostapi"] == mme]


def resolve_device(name):
    for i, n in input_devices():
        if n == name:
            return i
    return None  # system default


def speak(text):
    subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Add-Type -AssemblyName System.Speech; "
         f"(New-Object System.Speech.Synthesis.SpeechSynthesizer).Speak('{text}')"],
        check=False, creationflags=0x08000000)


def matches_command(text):
    words = re.findall(r"[a-z]+", text.lower())
    lock_at = next((i for i, w in enumerate(words) if w in ("lock", "luck", "lark")), None)
    if lock_at is None:
        return False
    head = words[:max(1, lock_at)]
    return any(difflib.SequenceMatcher(None, w, "firilla").ratio() > 0.5 for w in head)


class Segmenter:
    """Cuts a stream of 30 ms blocks into utterances using WebRTC VAD.

    Unlike a plain loudness threshold, the VAD ignores steady background noise
    (fans, hum, hiss), so a recording ends once the speech does.
    """
    MIN_RMS = 0.006       # ignore blocks quieter than this even if VAD says "speech"
    START_FRAMES = 6      # of the last 8 frames must be speech to start
    MIN_SPEECH = 0.25     # seconds of speech needed for a valid utterance

    def __init__(self, max_seconds=4.0, silence=0.6):
        import webrtcvad
        self.vad = webrtcvad.Vad(3)
        self.max_frames = int(max_seconds / 0.03)
        self.silence_frames = int(silence / 0.03)
        self.ring = []
        self.history = []
        self.chunks = None
        self.unvoiced = 0
        self.voiced = 0

    def _is_speech(self, block):
        rms = float(np.sqrt(np.mean(block ** 2)))
        if self.chunks is None:  # learn the room's noise floor while idle
            self.history = (self.history + [rms])[-100:]
        floor = float(np.percentile(self.history, 20)) if self.history else 0.0
        if rms < max(self.MIN_RMS, 2.5 * floor):  # must stand out from steady background
            return False
        pcm = (np.clip(block, -1, 1) * 32767).astype(np.int16).tobytes()
        return self.vad.is_speech(pcm, SR)

    def feed(self, block):
        """Returns the finished utterance (float32) or None."""
        speech = self._is_speech(block)
        if self.chunks is None:
            self.ring = (self.ring + [(block, speech)])[-8:]
            if sum(s for _, s in self.ring) >= self.START_FRAMES:
                self.chunks = [b for b, _ in self.ring]
                self.voiced = sum(s for _, s in self.ring)
                self.unvoiced = 0
            return None
        self.chunks.append(block)
        self.voiced += speech
        self.unvoiced = 0 if speech else self.unvoiced + 1
        if self.unvoiced >= self.silence_frames or len(self.chunks) >= self.max_frames:
            audio, voiced = np.concatenate(self.chunks), self.voiced * 0.03
            self.chunks, self.ring = None, []
            return audio if voiced >= self.MIN_SPEECH else None
        return None


class Engine:
    def __init__(self, log):
        self.log = log
        self.on_download = lambda done, total, finished: None
        self.level = 0.0
        self.sink = None
        self.stream = None
        self.stt = None
        self.enc = None
        self.stop_evt = threading.Event()
        self.busy = threading.Lock()

    # ---- microphone -------------------------------------------------
    def open_mic(self, device):
        self.close_mic()
        def cb(data, *_):
            block = data[:, 0].copy()
            self.level = float(np.sqrt(np.mean(block ** 2)))
            sink = self.sink
            if sink is not None:
                sink.put(block)
        self.stream = sd.InputStream(samplerate=SR, channels=1, dtype="float32",
                                     blocksize=BLOCK, device=device, callback=cb)
        self.stream.start()

    def close_mic(self):
        if self.stream:
            self.stream.close()
            self.stream = None
        self.level = 0.0

    def listen(self, max_seconds=4.0, silence=0.6):
        """Block until one utterance is captured. Returns audio, or None if stopped."""
        q = self.sink = queue.Queue()
        seg = Segmenter(max_seconds, silence)
        try:
            while not self.stop_evt.is_set():
                try:
                    block = q.get(timeout=0.2)
                except queue.Empty:
                    continue
                audio = seg.feed(block)
                if audio is not None:
                    return audio
            return None
        finally:
            self.sink = None

    # ---- models -----------------------------------------------------
    def load_voice_encoder(self):
        if self.enc is None:
            from resemblyzer import VoiceEncoder
            self.enc = VoiceEncoder("cpu")

    def load_whisper(self):
        if self.stt is None:
            if not whisper_ready():
                self.log("Downloading the speech model (~140 MB, one time only)...")
                try:
                    download_whisper(lambda d, t: self.on_download(d, t, False))
                except Exception as e:
                    self.on_download(0, 0, True)
                    raise RuntimeError(
                        "Couldn't download the speech model - check your internet connection. "
                        f"(Or copy the 'models' folder from another PC.) Details: {e}")
                self.on_download(0, 0, True)
                self.log("Speech model downloaded and saved in the 'models' folder.")
            self.log("Loading speech model...")
            from faster_whisper import WhisperModel
            self.stt = WhisperModel(str(WHISPER_DIR), device="cpu", compute_type="int8")

    def transcribe(self, audio):
        segs, _ = self.stt.transcribe(audio, language="en", beam_size=1,
                                      initial_prompt="Firilla lock. Firilla.")
        return " ".join(s.text for s in segs).strip()

    def embed(self, audio):
        from resemblyzer import preprocess_wav
        return self.enc.embed_utterance(preprocess_wav(audio, source_sr=SR))

    @staticmethod
    def enrolled():
        return VOICEPRINT.exists()

    def score(self, emb):
        mine = np.load(VOICEPRINT)
        return float(np.dot(emb, mine) / (np.linalg.norm(emb) * np.linalg.norm(mine)))

    # ---- actions ----------------------------------------------------
    def enroll(self, status, count=6):
        self.stop_evt.clear()
        self.load_voice_encoder()
        self.load_whisper()
        embeds, misses = [], 0
        while len(embeds) < count and not self.stop_evt.is_set():
            status(f'Sample {len(embeds) + 1}/{count} - say "{PHRASE}" now')
            audio = self.listen()
            if audio is None:
                break
            text = self.transcribe(audio)
            if not matches_command(text):
                misses += 1
                if misses < 4:
                    self.log(f"Heard {text!r} - that wasn't \"{PHRASE}\", try again.")
                    continue
                self.log(f"Heard {text!r} - accepting anyway (speech detected, not recognised).")
            misses = 0
            embeds.append(self.embed(audio))
            self.log(f"Sample {len(embeds)}/{count} recorded.")
            time.sleep(0.4)
        if len(embeds) == count:
            np.save(VOICEPRINT, np.mean(embeds, axis=0))
            self.log("Voiceprint saved.")
            return True
        self.log("Enrollment cancelled.")
        return False

    def test_once(self, threshold):
        """Record one phrase and report transcript + voice score (no locking)."""
        self.stop_evt.clear()
        self.load_voice_encoder()
        self.load_whisper()
        self.log(f'Say "{PHRASE}"...')
        audio = self.listen()
        if audio is None:
            return
        text = self.transcribe(audio)
        s = self.score(self.embed(audio))
        verdict = "would LOCK" if matches_command(text) and s >= threshold else "would be DENIED / ignored"
        self.log(f"Heard {text!r} | phrase match: {matches_command(text)} | "
                 f"voice score {s:.2f} (need {threshold:.2f}) -> {verdict}")

    def run(self, get_threshold, get_test_mode, state):
        self.stop_evt.clear()
        state("loading")
        self.load_voice_encoder()
        self.load_whisper()
        state("listening")
        self.log(f'Listening for "{PHRASE}"')
        while not self.stop_evt.is_set():
            audio = self.listen()
            if audio is None:
                break
            state("processing")
            text = self.transcribe(audio)
            if text and matches_command(text):
                s = self.score(self.embed(audio))
                thr = get_threshold()
                self.log(f"Heard {text!r} - voice score {s:.2f} (need {thr:.2f})")
                if s >= thr:
                    self.log("ACCEPTED - " + ("test mode, not locking" if get_test_mode() else "locking"))
                    speak("Yes master")
                    if not get_test_mode():
                        ctypes.windll.user32.LockWorkStation()
                        time.sleep(3)
                else:
                    self.log("DENIED")
                    speak("Firilla denied.")
            elif text:
                self.log(f"Heard {text!r} (ignored)")
            state("listening")
        state("stopped")
        self.log("Stopped.")
