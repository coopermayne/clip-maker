"""
GalipoLaw - CopClipper v2.0 — A modern GUI for clipping and slowing down videos with ffmpeg.
"""

import os
import re
import sys
import subprocess
import threading
import tkinter as tk
from tkinter import filedialog

import customtkinter as ctk

try:
    import windnd
    HAS_DND = True
except ImportError:
    HAS_DND = False

# --- Theme ---
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

ACCENT = "#6366f1"
ACCENT_HOVER = "#4f46e5"
SUCCESS = "#16a34a"
WARNING = "#d97706"
ERROR = "#dc2626"
MUTED = "#94a3b8"


def resource_path(filename):
    """Get path to bundled resource (works for PyInstaller and dev mode)."""
    if getattr(sys, "_MEIPASS", None):
        return os.path.join(sys._MEIPASS, filename)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)


def get_desktop_path():
    """Return the user's Desktop folder path."""
    return os.path.join(os.path.expanduser("~"), "Desktop")


def parse_timestamp(ts):
    """Parse H:MM:SS or HH:MM:SS into total seconds. Raises ValueError on bad input."""
    ts = ts.strip()
    match = re.fullmatch(r"(\d{1,2}):(\d{1,2}):(\d{1,2})", ts)
    if not match:
        raise ValueError(f"Bad timestamp format: '{ts}'. Use H:MM:SS or HH:MM:SS.")
    h, m, s = int(match.group(1)), int(match.group(2)), int(match.group(3))
    if m >= 60 or s >= 60:
        raise ValueError(f"Minutes/seconds must be < 60 in '{ts}'.")
    return h * 3600 + m * 60 + s


def build_ffmpeg_cmd(ffmpeg_path, input_file, start, end, speed, output_file):
    """Build the ffmpeg command list. speed is 0.1-1.0 (1 = normal, 0.5 = half speed)."""
    cmd = [ffmpeg_path, "-y", "-ss", start, "-to", end, "-i", input_file]

    if speed == 1.0:
        cmd += ["-c", "copy"]
    else:
        pts_multiplier = 1.0 / speed
        cmd += ["-filter:v", f"setpts={pts_multiplier:.4f}*PTS"]

        atempo_filters = []
        remaining = speed
        while remaining < 0.5:
            atempo_filters.append("atempo=0.5")
            remaining /= 0.5
        atempo_filters.append(f"atempo={remaining:.6f}")
        cmd += ["-filter:a", ",".join(atempo_filters)]

    cmd.append(output_file)
    return cmd


def seconds_to_timestamp(secs):
    """Convert total seconds (int or float) to H:MM:SS string."""
    secs = int(secs)
    h = secs // 3600
    m = (secs % 3600) // 60
    s = secs % 60
    return f"{h}:{m:02d}:{s:02d}"


class ClipMakerApp:
    SPEED_PRESETS = [
        ("1x", 1.0),
        ("75%", 0.75),
        ("66%", 0.6667),
        ("50%", 0.5),
        ("33%", 0.333),
        ("25%", 0.25),
    ]

    def __init__(self, root):
        self.root = root
        self.root.title("GalipoLaw - CopClipper")
        self.root.resizable(False, False)

        # Set window icon
        icon_path = resource_path("icon.ico")
        if os.path.isfile(icon_path):
            self.root.after(200, lambda: self.root.iconbitmap(icon_path))

        self.ffmpeg_path = self._find_ffmpeg()
        self.video_duration = 0
        self._syncing_slider = False
        self._active_speed_btn = None
        self._build_ui()
        self._setup_auto_name()
        self._setup_slider_sync()
        self.root.update_idletasks()
        self._center_window()

    def _find_ffmpeg(self):
        for name in ("ffmpeg.exe", "ffmpeg"):
            path = resource_path(name)
            if os.path.isfile(path):
                return path
        return "ffmpeg"

    def _find_ffprobe(self):
        for name in ("ffprobe.exe", "ffprobe"):
            path = resource_path(name)
            if os.path.isfile(path):
                return path
        return "ffprobe"

    def _center_window(self):
        w = self.root.winfo_width()
        h = self.root.winfo_height()
        x = (self.root.winfo_screenwidth() // 2) - (w // 2)
        y = (self.root.winfo_screenheight() // 3) - (h // 2)
        self.root.geometry(f"+{x}+{y}")

    def _build_ui(self):
        pad = 24

        outer = ctk.CTkFrame(self.root, fg_color="transparent")
        outer.pack(fill="both", expand=True, padx=pad, pady=pad)

        # --- Title ---
        ctk.CTkLabel(
            outer, text="GalipoLaw - CopClipper",
            font=ctk.CTkFont(size=22, weight="bold"),
        ).pack(pady=(0, 4))
        ctk.CTkLabel(
            outer, text="Clip and slow-mo your videos",
            font=ctk.CTkFont(size=13), text_color=MUTED,
        ).pack(pady=(0, 16))

        # --- Separator ---
        ctk.CTkFrame(outer, height=2, fg_color=("gray80", "gray30")).pack(fill="x", pady=(0, 16))

        # --- Drop zone ---
        self.file_var = tk.StringVar()

        self._drop_frame = ctk.CTkFrame(
            outer, corner_radius=12, border_width=2,
            border_color=ACCENT, fg_color=("gray92", "gray20"),
            height=80, cursor="hand2",
        )
        self._drop_frame.pack(fill="x", pady=(0, 4))
        self._drop_frame.pack_propagate(False)

        self.drop_label = ctk.CTkLabel(
            self._drop_frame,
            text="Drag & drop a video file here\nor click to Browse",
            font=ctk.CTkFont(size=13), text_color=ACCENT,
        )
        self.drop_label.pack(expand=True)

        self._drop_frame.bind("<Button-1>", lambda e: self._browse())
        self.drop_label.bind("<Button-1>", lambda e: self._browse())

        self.file_label = ctk.CTkLabel(
            outer, textvariable=self.file_var,
            font=ctk.CTkFont(size=11), text_color=MUTED,
            anchor="w", wraplength=460,
        )
        self.file_label.pack(fill="x", pady=(0, 12))

        if HAS_DND:
            windnd.hook_dropfiles(self.root, self._on_drop)

        # --- Form ---
        form = ctk.CTkFrame(outer, fg_color="transparent")
        form.pack(fill="x")
        form.columnconfigure(1, weight=1)

        row = 0

        # Start Time
        ctk.CTkLabel(form, text="Start Time", font=ctk.CTkFont(size=13)).grid(
            row=row, column=0, sticky="w", pady=8)
        start_frame = ctk.CTkFrame(form, fg_color="transparent")
        start_frame.grid(row=row, column=1, sticky="ew", pady=8, padx=(12, 0))
        self.start_var = tk.StringVar(value="0:00:00")
        ctk.CTkEntry(start_frame, textvariable=self.start_var, width=100,
                      font=ctk.CTkFont(size=13)).pack(side="left")
        self.start_slider = ctk.CTkSlider(
            start_frame, from_=0, to=1, width=220,
            command=self._on_start_slider_move, state="disabled",
            button_color=ACCENT, button_hover_color=ACCENT_HOVER,
            progress_color=ACCENT,
        )
        self.start_slider.pack(side="left", padx=(12, 0), fill="x", expand=True)
        row += 1

        # End Time
        ctk.CTkLabel(form, text="End Time", font=ctk.CTkFont(size=13)).grid(
            row=row, column=0, sticky="w", pady=8)
        end_frame = ctk.CTkFrame(form, fg_color="transparent")
        end_frame.grid(row=row, column=1, sticky="ew", pady=8, padx=(12, 0))
        self.end_var = tk.StringVar(value="0:00:00")
        ctk.CTkEntry(end_frame, textvariable=self.end_var, width=100,
                      font=ctk.CTkFont(size=13)).pack(side="left")
        self.end_slider = ctk.CTkSlider(
            end_frame, from_=0, to=1, width=220,
            command=self._on_end_slider_move, state="disabled",
            button_color=ACCENT, button_hover_color=ACCENT_HOVER,
            progress_color=ACCENT,
        )
        self.end_slider.pack(side="left", padx=(12, 0), fill="x", expand=True)
        row += 1

        # Speed
        ctk.CTkLabel(form, text="Speed", font=ctk.CTkFont(size=13)).grid(
            row=row, column=0, sticky="w", pady=8)
        speed_frame = ctk.CTkFrame(form, fg_color="transparent")
        speed_frame.grid(row=row, column=1, sticky="w", pady=8, padx=(12, 0))
        self.speed_var = tk.StringVar(value="1")
        ctk.CTkEntry(speed_frame, textvariable=self.speed_var, width=70,
                      font=ctk.CTkFont(size=13)).pack(side="left")
        ctk.CTkLabel(speed_frame, text="1 = normal, .5 = half speed",
                      font=ctk.CTkFont(size=11), text_color=MUTED).pack(
            side="left", padx=(12, 0))
        row += 1

        # Speed preset buttons
        preset_frame = ctk.CTkFrame(form, fg_color="transparent")
        preset_frame.grid(row=row, column=0, columnspan=2, sticky="w", pady=(0, 8))
        ctk.CTkLabel(preset_frame, text="Presets:",
                      font=ctk.CTkFont(size=11), text_color=MUTED).pack(
            side="left", padx=(0, 8))
        self._speed_buttons = {}
        for label, value in self.SPEED_PRESETS:
            btn = ctk.CTkButton(
                preset_frame, text=label, width=50, height=28,
                font=ctk.CTkFont(size=12), corner_radius=6,
                fg_color=("gray78", "gray30"), text_color=("gray20", "gray90"),
                hover_color=("gray70", "gray40"),
                command=lambda v=value, l=label: self._on_speed_preset(l, v),
            )
            btn.pack(side="left", padx=3)
            self._speed_buttons[label] = btn
        row += 1

        # Output Name
        ctk.CTkLabel(form, text="Output Name", font=ctk.CTkFont(size=13)).grid(
            row=row, column=0, sticky="w", pady=8)
        out_frame = ctk.CTkFrame(form, fg_color="transparent")
        out_frame.grid(row=row, column=1, sticky="ew", pady=8, padx=(12, 0))
        self.out_var = tk.StringVar()
        ctk.CTkEntry(out_frame, textvariable=self.out_var,
                      font=ctk.CTkFont(size=13)).pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(out_frame, text=".mp4", font=ctk.CTkFont(size=12),
                      text_color=MUTED).pack(side="left", padx=(6, 0))

        # --- Separator ---
        ctk.CTkFrame(outer, height=2, fg_color=("gray80", "gray30")).pack(fill="x", pady=(16, 16))

        # --- Start Button ---
        self.start_btn = ctk.CTkButton(
            outer, text="Start", height=42,
            font=ctk.CTkFont(size=15, weight="bold"),
            corner_radius=10, fg_color=ACCENT, hover_color=ACCENT_HOVER,
            command=self._on_start,
        )
        self.start_btn.pack(fill="x", pady=(0, 16))

        # --- Status ---
        status_frame = ctk.CTkFrame(outer, fg_color="transparent")
        status_frame.pack(fill="x")
        ctk.CTkLabel(status_frame, text="Status:",
                      font=ctk.CTkFont(size=12)).pack(side="left")
        self.status_var = tk.StringVar(value="Ready")
        self.status_label = ctk.CTkLabel(
            status_frame, textvariable=self.status_var,
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=ACCENT, anchor="w",
        )
        self.status_label.pack(side="left", padx=(8, 0))

    # --- Sync logic ---

    def _setup_auto_name(self):
        for var in (self.start_var, self.end_var, self.speed_var):
            var.trace_add("write", lambda *_: self._update_output_name())

    def _setup_slider_sync(self):
        self.start_var.trace_add("write", lambda *_: self._on_start_text_change())
        self.end_var.trace_add("write", lambda *_: self._on_end_text_change())
        self.speed_var.trace_add("write", lambda *_: self._on_speed_text_change())

    def _on_start_slider_move(self, val):
        if self._syncing_slider:
            return
        self._syncing_slider = True
        self.start_var.set(seconds_to_timestamp(int(val)))
        self._syncing_slider = False

    def _on_end_slider_move(self, val):
        if self._syncing_slider:
            return
        self._syncing_slider = True
        self.end_var.set(seconds_to_timestamp(int(val)))
        self._syncing_slider = False

    def _on_start_text_change(self):
        if self._syncing_slider or self.video_duration == 0:
            return
        try:
            secs = parse_timestamp(self.start_var.get())
            secs = min(secs, self.video_duration)
            self._syncing_slider = True
            self.start_slider.set(secs)
            self._syncing_slider = False
        except ValueError:
            pass

    def _on_end_text_change(self):
        if self._syncing_slider or self.video_duration == 0:
            return
        try:
            secs = parse_timestamp(self.end_var.get())
            secs = min(secs, self.video_duration)
            self._syncing_slider = True
            self.end_slider.set(secs)
            self._syncing_slider = False
        except ValueError:
            pass

    def _on_speed_preset(self, label, value):
        self.speed_var.set(str(value))
        self._highlight_speed_btn(label)

    def _highlight_speed_btn(self, active_label):
        self._active_speed_btn = active_label
        for lbl, btn in self._speed_buttons.items():
            if lbl == active_label:
                btn.configure(fg_color=ACCENT, text_color="white",
                              hover_color=ACCENT_HOVER)
            else:
                btn.configure(fg_color=("gray78", "gray30"),
                              text_color=("gray20", "gray90"),
                              hover_color=("gray70", "gray40"))

    def _on_speed_text_change(self):
        if self._active_speed_btn is None:
            return
        current = self.speed_var.get().strip()
        for label, value in self.SPEED_PRESETS:
            if label == self._active_speed_btn:
                if current == str(value):
                    return
                break
        self._highlight_speed_btn(None)

    # --- Duration detection ---

    def _probe_duration(self, filepath):
        self._set_status("Detecting video duration...", WARNING)

        def _run():
            try:
                ffprobe = self._find_ffprobe()
                result = subprocess.run(
                    [ffprobe, "-v", "error", "-show_entries",
                     "format=duration", "-of", "default=noprint_wrappers=1:nokey=1",
                     filepath],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                output = result.stdout.decode().strip()
                if not output or result.returncode != 0:
                    self.root.after(0, self._set_status,
                                    "Could not detect duration — type timestamps manually.", WARNING)
                    return
                duration = float(output)
                self.root.after(0, self._set_duration, duration)
            except FileNotFoundError:
                self.root.after(0, self._set_status,
                                "ffprobe not found — type timestamps manually.", WARNING)
            except Exception:
                self.root.after(0, self._set_status,
                                "Duration detect failed — type timestamps manually.", WARNING)
        threading.Thread(target=_run, daemon=True).start()

    def _set_duration(self, duration):
        self.video_duration = int(duration)
        steps = max(self.video_duration, 1)
        self.start_slider.configure(from_=0, to=self.video_duration,
                                     number_of_steps=steps, state="normal")
        self.end_slider.configure(from_=0, to=self.video_duration,
                                   number_of_steps=steps, state="normal")
        self._syncing_slider = True
        self.start_slider.set(0)
        self.end_slider.set(self.video_duration)
        self.start_var.set(seconds_to_timestamp(0))
        self.end_var.set(seconds_to_timestamp(self.video_duration))
        self._syncing_slider = False
        dur_str = seconds_to_timestamp(self.video_duration)
        self._set_status(f"Ready — video duration {dur_str}", ACCENT)

    # --- File handling ---

    def _on_drop(self, files):
        if files:
            path = files[0]
            if isinstance(path, bytes):
                path = path.decode("utf-8", errors="replace")
            path = path.strip().strip('"')
            self.file_var.set(path)
            self._update_drop_zone()
            self._update_output_name()
            self._probe_duration(path)

    def _update_drop_zone(self):
        self.drop_label.configure(text="File selected (drop another to change)",
                                   text_color=SUCCESS)
        self._drop_frame.configure(border_color=SUCCESS,
                                    fg_color=("gray92", "gray20"))

    def _browse(self):
        path = filedialog.askopenfilename(
            title="Select a video file",
            filetypes=[
                ("Video files", "*.mp4 *.avi *.mov *.mkv *.wmv *.flv *.webm"),
                ("All files", "*.*"),
            ],
        )
        if path:
            self.file_var.set(path)
            self._update_drop_zone()
            self._update_output_name()
            self._probe_duration(path)

    def _format_ts_for_filename(self, ts):
        return ts.strip().replace(":", ".")

    def _update_output_name(self):
        input_file = self.file_var.get().strip()
        if not input_file:
            return
        filename = input_file.replace("\\", "/").rsplit("/", 1)[-1]
        base = os.path.splitext(filename)[0]
        start = self._format_ts_for_filename(self.start_var.get())
        end = self._format_ts_for_filename(self.end_var.get())
        try:
            speed = float(self.speed_var.get().strip())
        except ValueError:
            speed = 1.0
        speed_str = f"{int(speed * 100)}pct"
        self.out_var.set(f"{base}_CLIP_{start}-{end}_{speed_str}")

    def _set_status(self, msg, color=ACCENT):
        self.status_var.set(msg)
        self.status_label.configure(text_color=color)

    # --- Validation & processing ---

    def _validate(self):
        input_file = self.file_var.get().strip().strip('"')
        if not input_file:
            raise ValueError("Please select a video file.")
        is_network = input_file.startswith("\\\\") or (
            len(input_file) >= 2 and input_file[1] == ":"
            and not os.path.isfile(input_file)
        )
        if not is_network and not os.path.isfile(input_file):
            raise ValueError(f"File not found: {input_file}")

        start_str = self.start_var.get().strip()
        end_str = self.end_var.get().strip()
        start_secs = parse_timestamp(start_str)
        end_secs = parse_timestamp(end_str)
        if self.video_duration > 0 and end_secs > self.video_duration:
            end_secs = self.video_duration
            end_str = seconds_to_timestamp(end_secs)
            self.end_var.set(end_str)
        if end_secs <= start_secs:
            raise ValueError("End time must be after start time.")

        try:
            speed = float(self.speed_var.get().strip())
        except ValueError:
            raise ValueError("Speed must be a number (0.1 to 1).")
        if not 0.1 <= speed <= 1.0:
            raise ValueError("Speed must be between 0.1 and 1.")

        out_name = self.out_var.get().strip()
        if not out_name:
            raise ValueError("Please enter an output file name.")
        out_name = re.sub(r'[<>:"/\\|?*]', "_", out_name)
        output_path = os.path.join(get_desktop_path(), out_name + ".mp4")

        return input_file, start_str, end_str, speed, output_path

    def _on_start(self):
        try:
            input_file, start, end, speed, output_path = self._validate()
        except ValueError as e:
            self._set_status(str(e), ERROR)
            return

        self.start_btn.configure(state="disabled")
        self._set_status("Processing...", WARNING)

        cmd = build_ffmpeg_cmd(self.ffmpeg_path, input_file, start, end, speed, output_path)
        thread = threading.Thread(target=self._run_ffmpeg, args=(cmd, output_path), daemon=True)
        thread.start()

    def _run_ffmpeg(self, cmd, output_path):
        try:
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if result.returncode != 0:
                err = result.stderr.decode(errors="replace").strip()
                last_line = err.split("\n")[-1] if err else "Unknown error"
                self.root.after(0, self._set_status, f"Error: {last_line}", ERROR)
            else:
                basename = os.path.basename(output_path)
                self.root.after(0, self._set_status,
                                f"Done! Saved to Desktop as {basename}", SUCCESS)
        except FileNotFoundError:
            self.root.after(0, self._set_status,
                            "Error: ffmpeg not found. Place ffmpeg next to this app or install it.",
                            ERROR)
        except Exception as e:
            self.root.after(0, self._set_status, f"Error: {e}", ERROR)
        finally:
            self.root.after(0, lambda: self.start_btn.configure(state="normal"))


def main():
    root = ctk.CTk()
    ClipMakerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
