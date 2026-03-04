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


class ClipMakerApp:
    PADDING = 20
    FIELD_PAD = 8

    def __init__(self, root):
        self.root = root
        self.root.title("Video Clip Maker")
        self.root.resizable(False, False)
        self.root.configure(bg="#f5f5f5")

        self.ffmpeg_path = self._find_ffmpeg()
        self._setup_styles()
        self._build_ui()
        self.root.update_idletasks()
        self._center_window()

    def _find_ffmpeg(self):
        for name in ("ffmpeg.exe", "ffmpeg"):
            path = resource_path(name)
            if os.path.isfile(path):
                return path
        return "ffmpeg"

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

        # Video File
        ttk.Label(form, text="Video File:").grid(row=row, column=0, sticky="w", pady=fp)
        file_frame = ttk.Frame(form)
        file_frame.grid(row=row, column=1, sticky="ew", pady=fp, padx=(8, 0))
        file_frame.columnconfigure(0, weight=1)
        self.file_var = tk.StringVar()
        self.file_entry = ttk.Entry(file_frame, textvariable=self.file_var, font=("Helvetica", 13))
        self.file_entry.grid(row=0, column=0, sticky="ew")
        ttk.Button(file_frame, text="Browse", command=self._browse).grid(row=0, column=1, padx=(6, 0))
        row += 1

        # Start Time
        ttk.Label(form, text="Start Time:").grid(row=row, column=0, sticky="w", pady=fp)
        self.start_var = tk.StringVar(value="0:00:00")
        ttk.Entry(form, textvariable=self.start_var, width=12, font=("Helvetica", 13)).grid(
            row=row, column=1, sticky="w", pady=fp, padx=(8, 0)
        )
        row += 1

        # End Time
        ttk.Label(form, text="End Time:").grid(row=row, column=0, sticky="w", pady=fp)
        self.end_var = tk.StringVar(value="0:00:00")
        ttk.Entry(form, textvariable=self.end_var, width=12, font=("Helvetica", 13)).grid(
            row=row, column=1, sticky="w", pady=fp, padx=(8, 0)
        )
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

        # Output Name
        ttk.Label(form, text="Output Name:").grid(row=row, column=0, sticky="w", pady=fp)
        out_frame = ttk.Frame(form)
        out_frame.grid(row=row, column=1, sticky="w", pady=fp, padx=(8, 0))
        self.out_var = tk.StringVar()
        ttk.Entry(out_frame, textvariable=self.out_var, width=22, font=("Helvetica", 13)).pack(side="left")
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

    def _set_status(self, msg, color="#2563eb"):
        self.status_var.set(msg)
        self.status_label.config(fg=color)

    def _validate(self):
        input_file = self.file_var.get().strip()
        if not input_file:
            raise ValueError("Please select a video file.")
        if not os.path.isfile(input_file):
            raise ValueError(f"File not found: {input_file}")

        start_str = self.start_var.get().strip()
        end_str = self.end_var.get().strip()
        start_secs = parse_timestamp(start_str)
        end_secs = parse_timestamp(end_str)
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
