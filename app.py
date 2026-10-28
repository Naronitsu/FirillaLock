"""Firilla Voice Lock - control panel."""
import queue
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox

import pystray
from PIL import ImageTk

import firilla
import icon

try:
    import winreg
except ImportError:
    winreg = None

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_NAME = "FirillaVoiceLock"

BG, CARD, TEXT, MUTED = "#f5eeff", "#ffffff", "#3b2a55", "#8d7aa8"
PURPLE, PURPLE_HI, GREEN, GREEN_HI, PINK, PINK_HI = (
    "#8e5bd1", "#7a45c0", "#4cb585", "#3da174", "#ec6f8e", "#d85b7a")
FONT, FONT_B = ("Segoe UI", 10), ("Segoe UI", 10, "bold")

# state -> (pill text, pill colour, speech-bubble message)
STATES = {
    "stopped": ("Napping", "#a99bc2", "Zzz... press Start when you're ready."),
    "loading": ("Waking up", "#e0a526", "Waking up my ears..."),
    "listening": ("Listening", GREEN, 'I\'m listening for "Firilla lock"!'),
    "processing": ("Thinking", "#4a8fe0", "Hmm, let me think..."),
}


def autostart_enabled():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, APP_NAME)
            return True
    except OSError:
        return False


def set_autostart(on):
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if on:
            exe = sys.executable.replace("python.exe", "pythonw.exe")
            script = firilla.HERE / "app.py"
            winreg.SetValueEx(k, APP_NAME, 0, winreg.REG_SZ, f'"{exe}" "{script}" --minimized')
        else:
            try:
                winreg.DeleteValue(k, APP_NAME)
            except FileNotFoundError:
                pass


class Btn(tk.Button):
    """Flat coloured button with a hover colour."""
    def __init__(self, parent, text, command, color=PURPLE, hover=PURPLE_HI, big=False):
        super().__init__(parent, text=text, command=command, bg=color, fg="white",
                         activebackground=hover, activeforeground="white", relief="flat",
                         bd=0, cursor="hand2", font=("Segoe UI", 12 if big else 10, "bold"),
                         padx=18 if big else 12, pady=8 if big else 5,
                         disabledforeground="#e6dcf5")
        self.color, self.hover = color, hover
        self.bind("<Enter>", lambda e: self["state"] == "normal" and self.configure(bg=self.hover))
        self.bind("<Leave>", lambda e: self.configure(bg=self.color))

    def recolor(self, color, hover):
        self.color, self.hover = color, hover
        self.configure(bg=color)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Firilla Voice Lock")
        self.geometry("540x800")
        self.minsize(500, 780)
        self.configure(bg=BG)
        self.cfg = firilla.load_config()
        self.events = queue.Queue()
        self.engine = firilla.Engine(lambda m: self.events.put(("log", m)))
        self.engine.on_download = lambda d, t, fin: self.events.put(("dl", (d, t, fin)))
        self.worker = None
        self.state_name = "stopped"
        self.devices = firilla.input_devices()
        self.icon_img = icon.make_icon(256)
        self.iconphoto(True, ImageTk.PhotoImage(self.icon_img))
        self.logo = ImageTk.PhotoImage(icon.make_icon(72))
        self._build()
        self._open_mic()
        self._refresh_enrolled()
        self._start_tray()
        self.protocol("WM_DELETE_WINDOW", self.withdraw)
        self.after(50, self._tick)
        if not firilla.whisper_ready():
            self._download_in_background()
        if not firilla.Engine.enrolled() and "--minimized" not in sys.argv:
            self.after(400, self._welcome)
        if "--minimized" in sys.argv:
            self.withdraw()
            if firilla.Engine.enrolled():
                self.after(500, self.toggle_run)

    # ---- layout -----------------------------------------------------
    def _card(self, title):
        outer = tk.Frame(self, bg=BG)
        outer.pack(fill="x", padx=16, pady=(0, 10))
        card = tk.Frame(outer, bg=CARD, highlightbackground="#e3d6f5", highlightthickness=1)
        card.pack(fill="x")
        tk.Label(card, text=title, bg=CARD, fg=PURPLE, font=FONT_B).pack(anchor="w", padx=14, pady=(10, 2))
        body = tk.Frame(card, bg=CARD)
        body.pack(fill="x", padx=14, pady=(0, 12))
        return body

    def _build(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TCombobox", fieldbackground="#faf6ff", background="#efe4ff", padding=4)
        style.configure("Horizontal.TProgressbar", troughcolor="#efe4ff", background=GREEN,
                        bordercolor=CARD, lightcolor=GREEN, darkcolor=GREEN, thickness=10)
        style.configure("Dl.Horizontal.TProgressbar", troughcolor="#efe4ff", background="#4a8fe0",
                        bordercolor=CARD, lightcolor="#4a8fe0", darkcolor="#4a8fe0", thickness=12)
        style.configure("Horizontal.TScale", background=CARD, troughcolor="#e3d6f5")
        style.configure("TCheckbutton", background=CARD, foreground=TEXT, font=FONT)
        style.map("TCheckbutton", background=[("active", CARD)])

        # header
        head = tk.Frame(self, bg=BG)
        head.pack(fill="x", padx=16, pady=(14, 4))
        tk.Label(head, image=self.logo, bg=BG).pack(side="left")
        titles = tk.Frame(head, bg=BG)
        titles.pack(side="left", padx=12)
        tk.Label(titles, text="Firilla", bg=BG, fg=TEXT, font=("Segoe UI", 22, "bold")).pack(anchor="w")
        tk.Label(titles, text="your voice-powered door lock", bg=BG, fg=MUTED, font=FONT).pack(anchor="w")
        self.pill = tk.Label(head, text="Napping", bg="#a99bc2", fg="white",
                             font=FONT_B, padx=12, pady=3)
        self.pill.pack(side="right")

        # speech bubble + start button
        bubble = tk.Frame(self, bg=CARD, highlightbackground="#e3d6f5", highlightthickness=1)
        bubble.pack(fill="x", padx=16, pady=(6, 10))
        self.bubble = tk.Label(bubble, text=STATES["stopped"][2], bg=CARD, fg=TEXT,
                               font=("Segoe UI", 11), anchor="w")
        self.bubble.pack(side="left", padx=14, pady=12)
        self.run_btn = Btn(bubble, "Start", self.toggle_run, GREEN, GREEN_HI, big=True)
        self.run_btn.pack(side="right", padx=10, pady=8)

        # model download panel (hidden until needed)
        self.dl_card = tk.Frame(self, bg=CARD, highlightbackground="#bcd5f5", highlightthickness=1)
        self.dl_label = tk.Label(self.dl_card, bg=CARD, fg=TEXT, font=FONT, anchor="w", justify="left",
                                 text="Downloading my speech brain (one time only, ~140 MB).\n"
                                      "It's saved in the 'models' folder, so it travels with the app.")
        self.dl_label.pack(fill="x", padx=14, pady=(10, 4))
        self.dl_bar = ttk.Progressbar(self.dl_card, maximum=100, style="Dl.Horizontal.TProgressbar")
        self.dl_bar.pack(fill="x", padx=14, pady=(0, 4))
        self.dl_pct = tk.Label(self.dl_card, bg=CARD, fg=MUTED, font=("Segoe UI", 9), anchor="w")
        self.dl_pct.pack(fill="x", padx=14, pady=(0, 10))

        # microphone
        mic = self._card("Microphone")
        self.dev_var = tk.StringVar()
        names = ["System default"] + [n for _, n in self.devices]
        self.dev_box = ttk.Combobox(mic, textvariable=self.dev_var, values=names, state="readonly")
        self.dev_var.set(self.cfg["device"] if self.cfg["device"] in names else names[0])
        self.dev_box.pack(fill="x", pady=(0, 8))
        self.dev_box.bind("<<ComboboxSelected>>", self._device_changed)
        self.meter = ttk.Progressbar(mic, maximum=100)
        self.meter.pack(fill="x")
        tk.Label(mic, text="Say something - the bar should dance.", bg=CARD, fg=MUTED,
                 font=("Segoe UI", 9)).pack(anchor="w", pady=(4, 0))

        # voice
        voice = self._card("Your voice")
        row = tk.Frame(voice, bg=CARD)
        row.pack(fill="x")
        self.enrolled_lbl = tk.Label(row, bg=CARD, fg=TEXT, font=FONT)
        self.enrolled_lbl.pack(side="left")
        self.test_btn = Btn(row, "Test", self.test_voice, "#b79ae0", PURPLE)
        self.test_btn.pack(side="right", padx=(6, 0))
        self.enroll_btn = Btn(row, "Enroll voice", self.enroll)
        self.enroll_btn.pack(side="right")
        self.prompt = tk.Label(voice, text="", bg=CARD, fg="#4a8fe0", font=FONT_B, anchor="w")
        self.prompt.pack(fill="x", pady=(6, 0))

        # settings
        sets = self._card("Settings")
        trow = tk.Frame(sets, bg=CARD)
        trow.pack(fill="x")
        tk.Label(trow, text="Voice strictness", bg=CARD, fg=TEXT, font=FONT).pack(side="left")
        self.thr_val = tk.Label(trow, bg=CARD, fg=PURPLE, font=FONT_B, width=5)
        self.thr_val.pack(side="right")
        self.thr = tk.DoubleVar(value=self.cfg["threshold"])
        ttk.Scale(sets, from_=0.5, to=0.95, variable=self.thr, command=self._thr_changed
                  ).pack(fill="x", pady=(2, 0))
        tk.Label(sets, text="Lower = easier to get in (others might too). Higher = pickier (you might "
                 "get denied).", bg=CARD, fg=MUTED, font=("Segoe UI", 9), wraplength=450,
                 justify="left").pack(anchor="w", pady=(0, 6))
        self.test_mode = tk.BooleanVar(value=self.cfg["test_mode"])
        ttk.Checkbutton(sets, text="Practice mode (answers, but doesn't actually lock)",
                        variable=self.test_mode, command=self._save).pack(anchor="w")
        self.auto = tk.BooleanVar(value=autostart_enabled())
        ttk.Checkbutton(sets, text="Wake up automatically when I log in",
                        variable=self.auto, command=self._autostart_changed).pack(anchor="w", pady=(2, 0))
        self._thr_changed()

        # log
        logf = tk.Frame(self, bg=BG)
        logf.pack(fill="both", expand=True, padx=16, pady=(0, 14))
        tk.Label(logf, text="Diary", bg=BG, fg=PURPLE, font=FONT_B).pack(anchor="w")
        box = tk.Frame(logf, bg="#e3d6f5", padx=1, pady=1)
        box.pack(fill="both", expand=True)
        self.log = tk.Text(box, height=6, state="disabled", wrap="word", font=("Consolas", 9),
                           bg="#fbf8ff", fg=TEXT, relief="flat", padx=8, pady=6)
        self.log.pack(fill="both", expand=True)

    # ---- helpers ----------------------------------------------------
    def _log(self, msg):
        self.log.configure(state="normal")
        self.log.insert("end", f"{time.strftime('%H:%M:%S')}  {msg}\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _set_state(self, name):
        self.state_name = name
        text, color, say = STATES[name]
        self.pill.configure(text=text, bg=color)
        self.bubble.configure(text=say)
        if name == "stopped":
            self.run_btn.configure(text="Start")
            self.run_btn.recolor(GREEN, GREEN_HI)
        else:
            self.run_btn.configure(text="Stop")
            self.run_btn.recolor(PINK, PINK_HI)
        self.tray.title = f"Firilla Voice Lock - {text}"
        self.tray.update_menu()

    def _start_tray(self):
        post = lambda what: (lambda *_: self.events.put(("tray", what)))
        menu = pystray.Menu(
            pystray.MenuItem("Open", post("show"), default=True),
            pystray.MenuItem(lambda _: "Stop listening" if self._busy() else "Start listening", post("toggle")),
            pystray.MenuItem("Quit", post("quit")),
        )
        self.tray = pystray.Icon("firilla", self.icon_img, "Firilla Voice Lock - Napping", menu)
        self.tray.run_detached()

    def _welcome(self):
        if messagebox.askyesno(
                "Welcome to Firilla!",
                "Let's set up your voice.\n\nPick your microphone first (watch the level bar move "
                "when you talk), then I'll ask you to say \"Firilla lock\" six times.\n\n"
                "Start enrollment now?"):
            self.enroll()

    def _show(self):
        self.deiconify()
        self.lift()
        self.focus_force()

    def _refresh_enrolled(self):
        ok = firilla.Engine.enrolled()
        self.enrolled_lbl.configure(text="I know your voice!" if ok else "I don't know your voice yet")
        self.test_btn.configure(state="normal" if ok else "disabled")
        self.enroll_btn.configure(text="Re-enroll" if ok else "Enroll voice")

    def _save(self):
        self.cfg.update(device=self.dev_var.get() if self.dev_var.get() != "System default" else None,
                        threshold=round(self.thr.get(), 2), test_mode=self.test_mode.get())
        firilla.save_config(self.cfg)

    def _thr_changed(self, *_):
        self.thr_val.configure(text=f"{self.thr.get():.2f}")
        self._save()

    def _autostart_changed(self):
        try:
            set_autostart(self.auto.get())
        except OSError as e:
            self.auto.set(not self.auto.get())
            messagebox.showerror("Autostart", str(e))

    def _busy(self):
        return self.worker is not None and self.worker.is_alive()

    def _open_mic(self):
        try:
            self.engine.open_mic(firilla.resolve_device(self.cfg["device"]))
        except Exception as e:
            self._log(f"Could not open microphone: {e}")

    def _device_changed(self, *_):
        if self._busy():
            self.engine.stop_evt.set()
        self._save()
        self._open_mic()

    def _spawn(self, fn, *args, done=None):
        def target():
            try:
                fn(*args)
            except Exception as e:
                self.events.put(("log", f"Error: {e}"))
            self.events.put(("done", done))
        self.worker = threading.Thread(target=target, daemon=True)
        self.worker.start()

    def _download_in_background(self):
        def target():
            try:
                self.events.put(("log", "First run: downloading the speech model (~140 MB, one time only)..."))
                firilla.download_whisper(lambda d, t: self.events.put(("dl", (d, t, False))))
                self.events.put(("log", "Speech model downloaded and saved in the 'models' folder."))
            except Exception as e:
                self.events.put(("log", "Couldn't download the speech model - check your internet "
                                        f"connection and restart. ({e})"))
            self.events.put(("dl", (0, 0, True)))
        threading.Thread(target=target, daemon=True).start()

    # ---- actions ----------------------------------------------------
    def toggle_run(self):
        if self._busy():
            self.engine.stop_evt.set()
            return
        if not firilla.Engine.enrolled():
            messagebox.showinfo("Enroll first", "Record your voice first with 'Enroll voice'.")
            return
        self._set_state("loading")
        self._spawn(self.engine.run, lambda: self.thr.get(), lambda: self.test_mode.get(),
                    lambda s: self.events.put(("state", s)))

    def enroll(self):
        if self._busy():
            messagebox.showinfo("Busy", "Stop listening first.")
            return
        for b in (self.enroll_btn, self.test_btn, self.run_btn):
            b.configure(state="disabled")
        self._spawn(self.engine.enroll, lambda m: self.events.put(("prompt", m)), done="enroll")

    def test_voice(self):
        if self._busy():
            messagebox.showinfo("Busy", "Stop listening first.")
            return
        self.prompt.configure(text=f'Say "{firilla.PHRASE}"...')
        self.test_btn.configure(state="disabled")
        self._spawn(self.engine.test_once, self.thr.get(), done="test")

    def _quit(self):
        self.engine.stop_evt.set()
        self.engine.close_mic()
        self.tray.stop()
        self.destroy()

    # ---- UI pump ----------------------------------------------------
    def _download_progress(self, done, total, finished):
        if finished:
            self.dl_card.pack_forget()
            return
        if not self.dl_card.winfo_ismapped():
            self.dl_card.pack(fill="x", padx=16, pady=(0, 10), after=self.bubble.master)
        pct = 100 * done / total if total else 0
        self.dl_bar["value"] = pct
        self.dl_pct.configure(text=f"{done / 1e6:.0f} of ~{total / 1e6:.0f} MB  ({pct:.0f}%)")

    def _tick(self):
        self.meter["value"] = min(100, self.engine.level * 600)
        try:
            while True:
                kind, val = self.events.get_nowait()
                if kind == "log":
                    self._log(val)
                elif kind == "state":
                    self._set_state(val)
                elif kind == "dl":
                    self._download_progress(*val)
                elif kind == "tray":
                    {"show": self._show, "toggle": self.toggle_run, "quit": self._quit}[val]()
                elif kind == "prompt":
                    self.prompt.configure(text=val)
                elif kind == "done":
                    self.prompt.configure(text="")
                    self.run_btn.configure(state="normal")
                    self.enroll_btn.configure(state="normal")
                    self._refresh_enrolled()
                    if val is None:
                        self._set_state("stopped")
        except queue.Empty:
            pass
        self.after(50, self._tick)


if __name__ == "__main__":
    App().mainloop()
