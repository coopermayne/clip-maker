"""
Video Clip Maker — A simple GUI for clipping and slowing down videos with ffmpeg.
"""

import os
import re
import sys
import subprocess
import threading
import tkinter as tk
from tkinter import ttk, filedialog

try:
    import windnd
    HAS_DND = True
except ImportError:
    HAS_DND = False


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
    PADDING = 20
    FIELD_PAD = 8

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
        self.root.title("Video Clip Maker")
        self.root.resizable(False, False)
        self.root.configure(bg="#f5f5f5")

        self.ffmpeg_path = self._find_ffmpeg()
        self.video_duration = 0
        self._syncing_slider = False
        self._active_speed_btn = None
        self._setup_styles()
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

    def _setup_styles(self):
        style = ttk.Style()
        style.theme_use("aqua" if sys.platform == "darwin" else "clam")

        bg = "#f5f5f5"
        style.configure("TFrame", background=bg)
        style.configure("TLabel", background=bg, font=("Helvetica", 13))
        style.configure("Hint.TLabel", background=bg, foreground="#888888", font=("Helvetica", 11))
        style.configure("Title.TLabel", background=bg, font=("Helvetica", 18, "bold"))
        style.configure("Status.TLabel", background=bg, font=("Helvetica", 12))
        style.configure("TButton", font=("Helvetica", 13))
        style.configure(
            "Start.TButton",
            font=("Helvetica", 14, "bold"),
            padding=(20, 8),
        )
        style.configure("TEntry", font=("Helvetica", 13))

    def _center_window(self):
        w = self.root.winfo_width()
        h = self.root.winfo_height()
        x = (self.root.winfo_screenwidth() // 2) - (w // 2)
        y = (self.root.winfo_screenheight() // 3) - (h // 2)
        self.root.geometry(f"+{x}+{y}")

    def _build_ui(self):
        p = self.PADDING
        fp = self.FIELD_PAD

        outer = ttk.Frame(self.root, padding=(p, p, p, p))
        outer.pack(fill="both", expand=True)

        # --- Title ---
        ttk.Label(outer, text="Video Clip Maker", style="Title.TLabel").pack(pady=(0, 16))

        # --- Separator ---
        ttk.Separator(outer, orient="horizontal").pack(fill="x", pady=(0, 12))

        # --- Form grid ---
        form = ttk.Frame(outer)
        form.pack(fill="x")
        form.columnconfigure(1, weight=1)

        row = 0

        # Video File — drop zone + browse
        self.file_var = tk.StringVar()
        drop_frame = tk.Frame(form, bg="#e0e7ff", highlightbackground="#6366f1",
                              highlightthickness=2, cursor="hand2")
        drop_frame.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(fp, 4))
        drop_frame.columnconfigure(0, weight=1)

        self.drop_label = tk.Label(
            drop_frame, text="Drag & drop a video file here\nor click Browse",
            bg="#e0e7ff", fg="#4338ca", font=("Helvetica", 12), pady=18,
        )
        self.drop_label.pack(fill="both", expand=True)
        drop_frame.bind("<Button-1>", lambda e: self._browse())
        self.drop_label.bind("<Button-1>", lambda e: self._browse())

        self.file_label = tk.Label(
            form, textvariable=self.file_var, bg="#f5f5f5", fg="#333",
            font=("Helvetica", 10), anchor="w", wraplength=400,
        )
        self.file_label.grid(row=row + 1, column=0, columnspan=2, sticky="ew", pady=(0, fp))

        if HAS_DND:
            windnd.hook_dropfiles(drop_frame, self._on_drop)
            windnd.hook_dropfiles(self.drop_label, self._on_drop)

        self._drop_frame = drop_frame
        row += 2

        # Start Time
        ttk.Label(form, text="Start Time:").grid(row=row, column=0, sticky="w", pady=fp)
        start_frame = ttk.Frame(form)
        start_frame.grid(row=row, column=1, sticky="ew", pady=fp, padx=(8, 0))
        self.start_var = tk.StringVar(value="0:00:00")
        ttk.Entry(start_frame, textvariable=self.start_var, width=10, font=("Helvetica", 13)).pack(side="left")
        self.start_slider = tk.Scale(
            start_frame, from_=0, to=1, orient="horizontal", length=200,
            resolution=1, showvalue=False, sliderlength=20,
            bg="#f5f5f5", troughcolor="#d1d5db", highlightthickness=0,
            command=self._on_start_slider_move,
        )
        self.start_slider.pack(side="left", padx=(10, 0), fill="x", expand=True)
        self.start_slider.config(state="disabled")
        row += 1

        # End Time
        ttk.Label(form, text="End Time:").grid(row=row, column=0, sticky="w", pady=fp)
        end_frame = ttk.Frame(form)
        end_frame.grid(row=row, column=1, sticky="ew", pady=fp, padx=(8, 0))
        self.end_var = tk.StringVar(value="0:00:00")
        ttk.Entry(end_frame, textvariable=self.end_var, width=10, font=("Helvetica", 13)).pack(side="left")
        self.end_slider = tk.Scale(
            end_frame, from_=0, to=1, orient="horizontal", length=200,
            resolution=1, showvalue=False, sliderlength=20,
            bg="#f5f5f5", troughcolor="#d1d5db", highlightthickness=0,
            command=self._on_end_slider_move,
        )
        self.end_slider.pack(side="left", padx=(10, 0), fill="x", expand=True)
        self.end_slider.config(state="disabled")
        row += 1

        # Speed
        ttk.Label(form, text="Speed:").grid(row=row, column=0, sticky="w", pady=fp)
        speed_frame = ttk.Frame(form)
        speed_frame.grid(row=row, column=1, sticky="w", pady=fp, padx=(8, 0))
        self.speed_var = tk.StringVar(value="1")
        ttk.Entry(speed_frame, textvariable=self.speed_var, width=6, font=("Helvetica", 13)).pack(side="left")
        ttk.Label(speed_frame, text="1 = normal, .5 = half speed", style="Hint.TLabel").pack(
            side="left", padx=(10, 0)
        )
        row += 1

        # Speed preset buttons
        preset_frame = ttk.Frame(form)
        preset_frame.grid(row=row, column=0, columnspan=2, sticky="w", pady=(0, fp), padx=(0, 0))
        ttk.Label(preset_frame, text="Presets:", style="Hint.TLabel").pack(side="left", padx=(0, 8))
        self._speed_buttons = {}
        for label, value in self.SPEED_PRESETS:
            btn = tk.Button(
                preset_frame, text=label, font=("Helvetica", 11), width=4,
                relief="groove", bg="#e5e7eb", fg="#333", cursor="hand2",
                command=lambda v=value, l=label: self._on_speed_preset(l, v),
            )
            btn.pack(side="left", padx=2)
            self._speed_buttons[label] = btn
        row += 1

        # Output Name (auto-generated, editable)
        ttk.Label(form, text="Output Name:").grid(row=row, column=0, sticky="w", pady=fp)
        out_frame = ttk.Frame(form)
        out_frame.grid(row=row, column=1, sticky="ew", pady=fp, padx=(8, 0))
        out_frame.columnconfigure(0, weight=1)
        self.out_var = tk.StringVar()
        ttk.Entry(out_frame, textvariable=self.out_var, font=("Helvetica", 13)).pack(side="left", fill="x", expand=True)
        ttk.Label(out_frame, text=".mp4", style="Hint.TLabel").pack(side="left", padx=(4, 0))

        # --- Separator ---
        ttk.Separator(outer, orient="horizontal").pack(fill="x", pady=(16, 12))

        # --- Start Button ---
        self.start_btn = ttk.Button(
            outer, text="Start", style="Start.TButton", command=self._on_start
        )
        self.start_btn.pack(pady=(0, 12))

        # --- Status ---
        status_frame = ttk.Frame(outer)
        status_frame.pack(fill="x")
        ttk.Label(status_frame, text="Status:", style="Status.TLabel").pack(side="left")
        self.status_var = tk.StringVar(value="Ready")
        self.status_label = tk.Label(
            status_frame,
            textvariable=self.status_var,
            fg="#2563eb",
            bg="#f5f5f5",
            font=("Helvetica", 12, "bold"),
            anchor="w",
        )
        self.status_label.pack(side="left", padx=(8, 0))

    def _setup_auto_name(self):
        """Auto-update output name when timestamps or speed change."""
        for var in (self.start_var, self.end_var, self.speed_var):
            var.trace_add("write", lambda *_: self._update_output_name())

    def _setup_slider_sync(self):
        """Sync text fields to sliders when user types."""
        self.start_var.trace_add("write", lambda *_: self._on_start_text_change())
        self.end_var.trace_add("write", lambda *_: self._on_end_text_change())
        self.speed_var.trace_add("write", lambda *_: self._on_speed_text_change())

    def _on_start_slider_move(self, val):
        """Slider moved — update text field."""
        if self._syncing_slider:
            return
        self._syncing_slider = True
        self.start_var.set(seconds_to_timestamp(int(float(val))))
        self._syncing_slider = False

    def _on_end_slider_move(self, val):
        """Slider moved — update text field."""
        if self._syncing_slider:
            return
        self._syncing_slider = True
        self.end_var.set(seconds_to_timestamp(int(float(val))))
        self._syncing_slider = False

    def _on_start_text_change(self):
        """Text field changed — update slider."""
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
        """Text field changed — update slider."""
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
        """Speed preset button clicked."""
        self.speed_var.set(str(value))
        self._highlight_speed_btn(label)

    def _highlight_speed_btn(self, active_label):
        """Highlight the active speed button, unhighlight others."""
        self._active_speed_btn = active_label
        for lbl, btn in self._speed_buttons.items():
            if lbl == active_label:
                btn.config(bg="#6366f1", fg="white", relief="sunken")
            else:
                btn.config(bg="#e5e7eb", fg="#333", relief="groove")

    def _on_speed_text_change(self):
        """Clear speed button highlight if user manually edits speed field."""
        if self._active_speed_btn is None:
            return
        current = self.speed_var.get().strip()
        # Check if current value matches active preset
        for label, value in self.SPEED_PRESETS:
            if label == self._active_speed_btn:
                if current == str(value):
                    return
                break
        self._highlight_speed_btn(None)

    def _probe_duration(self, filepath):
        """Run ffprobe in background to get video duration."""
        self._set_status("Detecting video duration...", "#d97706")

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
                                    "Could not detect duration — type timestamps manually.", "#d97706")
                    return
                duration = float(output)
                self.root.after(0, self._set_duration, duration)
            except FileNotFoundError:
                self.root.after(0, self._set_status,
                                "ffprobe not found — type timestamps manually.", "#d97706")
            except Exception as e:
                self.root.after(0, self._set_status,
                                f"Duration detect failed — type timestamps manually.", "#d97706")
        threading.Thread(target=_run, daemon=True).start()

    def _set_duration(self, duration):
        """Set video duration and enable/configure sliders."""
        self.video_duration = int(duration)
        # Reconfigure slider ranges and enable them
        self.start_slider.config(from_=0, to=self.video_duration, state="normal")
        self.end_slider.config(from_=0, to=self.video_duration, state="normal")
        # Set initial positions
        self._syncing_slider = True
        self.start_slider.set(0)
        self.end_slider.set(self.video_duration)
        self.start_var.set(seconds_to_timestamp(0))
        self.end_var.set(seconds_to_timestamp(self.video_duration))
        self._syncing_slider = False
        dur_str = seconds_to_timestamp(self.video_duration)
        self._set_status(f"Ready — video duration {dur_str}", "#2563eb")

    def _on_drop(self, files):
        """Handle files dropped onto the window."""
        if files:
            path = files[0]
            if isinstance(path, bytes):
                path = path.decode("utf-8", errors="replace")
            path = path.strip().strip('"')
            self.file_var.set(path)
            self._update_drop_zone(path)
            self._update_output_name()
            self._probe_duration(path)

    def _update_drop_zone(self, path):
        """Update the drop zone appearance after a file is selected."""
        self.drop_label.config(text="File selected (drop another to change)", fg="#16a34a")
        self._drop_frame.config(bg="#dcfce7", highlightbackground="#16a34a")
        self.drop_label.config(bg="#dcfce7")

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
            self._update_drop_zone(path)
            self._update_output_name()
            self._probe_duration(path)

    def _format_ts_for_filename(self, ts):
        """Convert H:MM:SS to H.MM.SS for filenames."""
        return ts.strip().replace(":", ".")

    def _update_output_name(self):
        """Auto-generate output name from file, timestamps, and speed."""
        input_file = self.file_var.get().strip()
        if not input_file:
            return
        # Handle both Unix and Windows path separators
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

    def _set_status(self, msg, color="#2563eb"):
        self.status_var.set(msg)
        self.status_label.config(fg=color)

    def _validate(self):
        input_file = self.file_var.get().strip().strip('"')
        if not input_file:
            raise ValueError("Please select a video file.")
        # Allow UNC paths (\\server\share) and mapped drives — skip check for network paths
        is_network = input_file.startswith("\\\\") or (len(input_file) >= 2 and input_file[1] == ":" and not os.path.isfile(input_file))
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
            self._set_status(str(e), "#dc2626")
            return

        self.start_btn.config(state="disabled")
        self._set_status("Processing...", "#d97706")

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
                self.root.after(0, self._set_status, f"Error: {last_line}", "#dc2626")
            else:
                basename = os.path.basename(output_path)
                self.root.after(0, self._set_status, f"Done! Saved to Desktop as {basename}", "#16a34a")
        except FileNotFoundError:
            self.root.after(
                0,
                self._set_status,
                "Error: ffmpeg not found. Place ffmpeg next to this app or install it.",
                "#dc2626",
            )
        except Exception as e:
            self.root.after(0, self._set_status, f"Error: {e}", "#dc2626")
        finally:
            self.root.after(0, lambda: self.start_btn.config(state="normal"))


def main():
    root = tk.Tk()
    ClipMakerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
