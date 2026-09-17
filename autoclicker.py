"""
کلیکر خودکار حرفه‌ای - نسخه نهایی
دو حالت مستقل: فوری | زمان‌بندی
نیازمندی: pip install pynput
"""

import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time
import json
import os
import sys
import ctypes
from datetime import datetime, timezone, timedelta

from pynput.mouse import Button, Controller
from pynput import keyboard

# ============================================================
# فعال‌سازی دقت 1ms در ویندوز (بجای 15.6ms پیش‌فرض)
# ============================================================
if sys.platform == "win32":
    try:
        ctypes.windll.winmm.timeBeginPeriod(1)
    except Exception:
        pass

# ============================================================
# ثابت‌ها و متغیرهای سراسری
# ============================================================
IRAN_TZ = timezone(timedelta(hours=3, minutes=30))
mouse = Controller()

running = False
stop_flag = False
waiting = False
wait_stop_flag = False
click_count = 0
CONFIG_FILE = os.path.join(
    os.path.dirname(os.path.abspath(sys.argv[0])),
    "autoclicker_config.json"
)

# ============================================================
# توابع کمکی
# ============================================================
def iran_now() -> datetime:
    """زمان لحظه‌ای به وقت ایران"""
    return datetime.now(IRAN_TZ)


def load_config() -> dict:
    """بارگذاری تنظیمات"""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "button": "چپ",
        "click_type": "یک‌بار",
        "hours": 0, "minutes": 0, "seconds": 0, "ms": 100,
        "mode": "موقعیت فعلی ماوس", "x": 0, "y": 0,
        "repeat_mode": "بی‌نهایت", "repeat_count": 100,
        "hotkey": "F6",
        "work_mode": "immediate",  # immediate | scheduled
        "sch_h": 12, "sch_m": 0, "sch_s": 0, "sch_ms": 0,
    }


def save_config(cfg: dict) -> None:
    """ذخیره تنظیمات"""
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


# ============================================================
# کلاس اصلی برنامه
# ============================================================
class AutoClicker:
    def __init__(self, root):
        self.root = root
        self.root.title("کلیکر خودکار حرفه‌ای")
        self.root.geometry("480x900")
        self.root.resizable(False, False)
        self.root.configure(bg="#f0f0f0")

        self.cfg = load_config()
        self.listener = None
        self.worker_thread = None
        self.waiter_thread = None

        self._build_ui()
        self._load_to_ui()
        self._start_hotkey_listener()
        self._tick_clock()

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ========================================================
    # ساخت رابط کاربری
    # ========================================================
    def _build_ui(self):
        pad = {"padx": 10, "pady": 4}

        # ---------- ساعت ایران ----------
        clock_frame = tk.Frame(self.root, bg="#1a237e")
        clock_frame.pack(fill="x", **pad)

        tk.Label(
            clock_frame, text="🕐 ساعت ایران (به وقت تهران)",
            bg="#1a237e", fg="#b0bec5", font=("Tahoma", 9)
        ).pack(pady=(6, 0))

        self.clock_label = tk.Label(
            clock_frame, text="00:00:00.000",
            bg="#1a237e", fg="#4fc3f7",
            font=("Consolas", 22, "bold")
        )
        self.clock_label.pack(pady=2)

        self.date_label = tk.Label(
            clock_frame, text="—",
            bg="#1a237e", fg="#cfd8dc", font=("Tahoma", 9)
        )
        self.date_label.pack()

        self.countdown_label = tk.Label(
            clock_frame, text="",
            bg="#1a237e", fg="#ffb74d",
            font=("Consolas", 12, "bold")
        )
        self.countdown_label.pack(pady=(2, 6))

        # ---------- انتخاب حالت کاری ----------
        mode_frame = tk.Frame(self.root, bg="#f0f0f0")
        mode_frame.pack(fill="x", **pad)

        self.work_mode_var = tk.StringVar(value="immediate")

        self.btn_mode_immediate = tk.Button(
            mode_frame, text="⚡  حالت ۱: فوری",
            font=("Tahoma", 11, "bold"),
            relief="solid", bd=2, cursor="hand2",
            command=lambda: self._set_work_mode("immediate")
        )
        self.btn_mode_immediate.pack(side="right", expand=True, fill="x", padx=3, pady=3)

        self.btn_mode_scheduled = tk.Button(
            mode_frame, text="⏰  حالت ۲: زمان‌بندی",
            font=("Tahoma", 11, "bold"),
            relief="solid", bd=2, cursor="hand2",
            command=lambda: self._set_work_mode("scheduled")
        )
        self.btn_mode_scheduled.pack(side="left", expand=True, fill="x", padx=3, pady=3)

        # ---------- پیام راهنما ----------
        self.info_label = tk.Label(
            self.root,
            text="⚡ در این حالت با زدن «شروع»، کلیکر بلافاصله کار می‌کند.",
            bg="#e3f2fd", fg="#1565c0",
            font=("Tahoma", 9), wraplength=440,
            pady=6, relief="solid", bd=1
        )
        self.info_label.pack(fill="x", **pad)

        # ---------- زمان‌بندی ----------
        self.sch_frame = tk.LabelFrame(
            self.root, text="⏰ زمان شروع خودکار (به وقت ایران)",
            font=("Tahoma", 10, "bold"), fg="#e65100",
            bg="#fff8e1"
        )
        self.sch_frame.pack(fill="x", **pad)

        row1 = tk.Frame(self.sch_frame, bg="#fff8e1")
        row1.pack(pady=4)

        tk.Label(row1, text="ساعت:", bg="#fff8e1").pack(side="right")
        self.sch_h_var = tk.IntVar(value=12)
        self.sch_h_sp = tk.Spinbox(row1, from_=0, to=23, width=3, textvariable=self.sch_h_var)
        self.sch_h_sp.pack(side="right", padx=2)

        tk.Label(row1, text=":", bg="#fff8e1").pack(side="right")
        self.sch_m_var = tk.IntVar(value=0)
        self.sch_m_sp = tk.Spinbox(row1, from_=0, to=59, width=3, textvariable=self.sch_m_var)
        self.sch_m_sp.pack(side="right", padx=2)

        tk.Label(row1, text=":", bg="#fff8e1").pack(side="right")
        self.sch_s_var = tk.IntVar(value=0)
        self.sch_s_sp = tk.Spinbox(row1, from_=0, to=59, width=3, textvariable=self.sch_s_var)
        self.sch_s_sp.pack(side="right", padx=2)

        tk.Label(row1, text=".", bg="#fff8e1").pack(side="right")
        self.sch_ms_var = tk.IntVar(value=0)
        self.sch_ms_sp = tk.Spinbox(row1, from_=0, to=999, width=4, textvariable=self.sch_ms_var)
        self.sch_ms_sp.pack(side="right", padx=2)

        row2 = tk.Frame(self.sch_frame, bg="#fff8e1")
        row2.pack(pady=(0, 6))

        self.btn_now = tk.Button(
            row2, text="🕐 الان + 5 ثانیه",
            bg="#c8e6c9", font=("Tahoma", 9), cursor="hand2",
            command=self._set_schedule_now
        )
        self.btn_now.pack(side="right", padx=4)

        self.btn_clear = tk.Button(
            row2, text="🗑️ پاک کردن",
            bg="#c8e6c9", font=("Tahoma", 9), cursor="hand2",
            command=self._clear_schedule
        )
        self.btn_clear.pack(side="right", padx=4)

        # ---------- دکمه ماوس ----------
        f1 = ttk.LabelFrame(self.root, text="دکمه ماوس")
        f1.pack(fill="x", **pad)
        self.btn_var = tk.StringVar(value="چپ")
        for t in ["وسط", "راست", "چپ"]:
            ttk.Radiobutton(
                f1, text=t, value=t, variable=self.btn_var
            ).pack(side="right", padx=8, pady=4)

        # ---------- نوع کلیک ----------
        f2 = ttk.LabelFrame(self.root, text="نوع کلیک")
        f2.pack(fill="x", **pad)
        self.click_type_var = tk.StringVar(value="یک‌بار")
        for t in ["دو‌بار", "یک‌بار"]:
            ttk.Radiobutton(
                f2, text=t, value=t, variable=self.click_type_var
            ).pack(side="right", padx=8, pady=4)

        # ---------- فاصله زمانی ----------
        f3 = ttk.LabelFrame(self.root, text="فاصله بین کلیک‌ها")
        f3.pack(fill="x", **pad)
        inner = tk.Frame(f3)
        inner.pack(pady=5)

        tk.Label(inner, text="ساعت:").pack(side="right")
        self.h_var = tk.IntVar(value=0)
        tk.Spinbox(inner, from_=0, to=99, width=3, textvariable=self.h_var).pack(side="right", padx=2)

        tk.Label(inner, text="دقیقه:").pack(side="right")
        self.m_var = tk.IntVar(value=0)
        tk.Spinbox(inner, from_=0, to=59, width=3, textvariable=self.m_var).pack(side="right", padx=2)

        tk.Label(inner, text="ثانیه:").pack(side="right")
        self.s_var = tk.IntVar(value=0)
        tk.Spinbox(inner, from_=0, to=59, width=3, textvariable=self.s_var).pack(side="right", padx=2)

        tk.Label(inner, text="میلی‌ثانیه:").pack(side="right")
        self.ms_var = tk.IntVar(value=100)
        tk.Spinbox(inner, from_=1, to=999, width=4, textvariable=self.ms_var).pack(side="right", padx=2)

        # ---------- موقعیت کلیک ----------
        f4 = ttk.LabelFrame(self.root, text="موقعیت کلیک")
        f4.pack(fill="x", **pad)

        self.pos_mode_var = tk.StringVar(value="موقعیت فعلی ماوس")
        ttk.Radiobutton(
            f4, text="موقعیت فعلی ماوس",
            value="موقعیت فعلی ماوس",
            variable=self.pos_mode_var,
            command=self._toggle_coords
        ).pack(anchor="e", padx=8, pady=2)

        ttk.Radiobutton(
            f4, text="مختصات دستی",
            value="مختصات دستی",
            variable=self.pos_mode_var,
            command=self._toggle_coords
        ).pack(anchor="e", padx=8, pady=2)

        coord_row = tk.Frame(f4)
        coord_row.pack(pady=5)

        tk.Label(coord_row, text="X:").pack(side="right")
        self.x_var = tk.IntVar(value=0)
        self.x_entry = tk.Entry(coord_row, textvariable=self.x_var, width=6)
        self.x_entry.pack(side="right", padx=3)

        tk.Label(coord_row, text="Y:").pack(side="right")
        self.y_var = tk.IntVar(value=0)
        self.y_entry = tk.Entry(coord_row, textvariable=self.y_var, width=6)
        self.y_entry.pack(side="right", padx=3)

        tk.Button(
            coord_row, text="📍 گرفتن موقعیت",
            bg="#c8e6c9", font=("Tahoma", 9), cursor="hand2",
            command=self._pick_position
        ).pack(side="right", padx=5)

        # ---------- تعداد کلیک ----------
        f5 = ttk.LabelFrame(self.root, text="تعداد کلیک")
        f5.pack(fill="x", **pad)

        self.repeat_var = tk.StringVar(value="بی‌نهایت")
        ttk.Radiobutton(
            f5, text="بی‌نهایت", value="بی‌نهایت",
            variable=self.repeat_var, command=self._toggle_repeat
        ).pack(anchor="e", padx=8, pady=2)

        rep_row = tk.Frame(f5)
        rep_row.pack(anchor="e", padx=8, pady=2)
        ttk.Radiobutton(
            rep_row, text="تعداد مشخص:", value="تعداد مشخص",
            variable=self.repeat_var, command=self._toggle_repeat
        ).pack(side="right")
        self.repeat_count_var = tk.IntVar(value=100)
        self.repeat_entry = tk.Entry(rep_row, textvariable=self.repeat_count_var, width=8)
        self.repeat_entry.pack(side="right", padx=5)

        # ---------- کلید میانبر ----------
        f6 = ttk.LabelFrame(self.root, text="کلید میانبر شروع/توقف")
        f6.pack(fill="x", **pad)

        self.hotkey_var = tk.StringVar(value="F6")
        hotkeys = [f"F{i}" for i in range(1, 13)]
        ttk.Combobox(
            f6, textvariable=self.hotkey_var, values=hotkeys,
            state="readonly", width=8
        ).pack(pady=5)

        # ---------- وضعیت ----------
        status_frame = tk.Frame(self.root, bg="#e8e8e8", relief="solid", bd=1)
        status_frame.pack(fill="x", **pad)

        self.status_label = tk.Label(
            status_frame, text="⏸ آماده",
            bg="#e8e8e8", fg="#888",
            font=("Tahoma", 11, "bold")
        )
        self.status_label.pack(side="right", padx=10, pady=8)

        self.count_label = tk.Label(
            status_frame, text="تعداد کلیک: 0",
            bg="#e8e8e8", fg="#333",
            font=("Consolas", 11, "bold")
        )
        self.count_label.pack(side="left", padx=10, pady=8)

        # ---------- دکمه‌های کنترل ----------
        ctrl_frame = tk.Frame(self.root)
        ctrl_frame.pack(fill="x", **pad)

        self.start_btn = tk.Button(
            ctrl_frame, text="▶ شروع",
            font=("Tahoma", 13, "bold"),
            bg="#43a047", fg="white",
            relief="raised", bd=2, cursor="hand2",
            command=self.start_clicking
        )
        self.start_btn.pack(side="right", expand=True, fill="x", padx=3, pady=5)

        self.stop_btn = tk.Button(
            ctrl_frame, text="⏹ توقف",
            font=("Tahoma", 13, "bold"),
            bg="#e53935", fg="white",
            relief="raised", bd=2, cursor="hand2",
            state="disabled",
            command=self.stop_clicking
        )
        self.stop_btn.pack(side="left", expand=True, fill="x", padx=3, pady=5)

        # ---------- هشدار ----------
        tk.Label(
            self.root,
            text="برای توقف اضطراری کلید ESC را بزنید",
            bg="#ffebee", fg="#d32f2f",
            font=("Tahoma", 9), pady=5
        ).pack(fill="x", **pad)

        # اعمال وضعیت اولیه
        self._set_work_mode(self.cfg.get("work_mode", "immediate"))
        self._toggle_coords()
        self._toggle_repeat()

    # ========================================================
    # مدیریت حالت کاری
    # ========================================================
    def _set_work_mode(self, mode: str):
        if running or waiting:
            messagebox.showwarning("هشدار", "ابتدا کلیکر را متوقف کنید.")
            return

        self.work_mode_var.set(mode)

        if mode == "immediate":
            self.btn_mode_immediate.config(bg="#e3f2fd", fg="#1565c0", relief="sunken")
            self.btn_mode_scheduled.config(bg="#f0f0f0", fg="#333", relief="solid")
            self.info_label.config(
                text="⚡ در این حالت با زدن «شروع»، کلیکر بلافاصله کار می‌کند."
            )
            self._disable_schedule_inputs()
        else:
            self.btn_mode_immediate.config(bg="#f0f0f0", fg="#333", relief="solid")
            self.btn_mode_scheduled.config(bg="#e3f2fd", fg="#1565c0", relief="sunken")
            self.info_label.config(
                text="⏰ در این حالت با زدن «شروع»، کلیکر در زمان تنظیم‌شده شروع می‌شود."
            )
            self._enable_schedule_inputs()

    def _enable_schedule_inputs(self):
        for w in [self.sch_h_sp, self.sch_m_sp, self.sch_s_sp,
                  self.sch_ms_sp, self.btn_now, self.btn_clear]:
            w.config(state="normal")

    def _disable_schedule_inputs(self):
        for w in [self.sch_h_sp, self.sch_m_sp, self.sch_s_sp,
                  self.sch_ms_sp, self.btn_now, self.btn_clear]:
            w.config(state="disabled")

    # ========================================================
    # توابع کمکی UI
    # ========================================================
    def _toggle_coords(self):
        state = "normal" if self.pos_mode_var.get() == "مختصات دستی" else "disabled"
        self.x_entry.config(state=state)
        self.y_entry.config(state=state)

    def _toggle_repeat(self):
        state = "normal" if self.repeat_var.get() == "تعداد مشخص" else "disabled"
        self.repeat_entry.config(state=state)

    def _pick_position(self):
        self.root.withdraw()
        messagebox.showinfo("گرفتن موقعیت",
                            "ماوس را روی نقطه مورد نظر ببرید.\n۳ ثانیه صبر کنید...")
        time.sleep(3)
        x, y = mouse.position
        self.x_var.set(int(x))
        self.y_var.set(int(y))
        self.pos_mode_var.set("مختصات دستی")
        self._toggle_coords()
        self.root.deiconify()

    def _set_schedule_now(self):
        target = iran_now() + timedelta(seconds=5)
        self.sch_h_var.set(target.hour)
        self.sch_m_var.set(target.minute)
        self.sch_s_var.set(target.second)
        self.sch_ms_var.set(target.microsecond // 1000)

    def _clear_schedule(self):
        self.sch_h_var.set(0)
        self.sch_m_var.set(0)
        self.sch_s_var.set(0)
        self.sch_ms_var.set(0)

    # ========================================================
    # بارگذاری/جمع‌آوری تنظیمات
    # ========================================================
    def _load_to_ui(self):
        c = self.cfg
        self.btn_var.set(c.get("button", "چپ"))
        self.click_type_var.set(c.get("click_type", "یک‌بار"))
        self.h_var.set(c.get("hours", 0))
        self.m_var.set(c.get("minutes", 0))
        self.s_var.set(c.get("seconds", 0))
        self.ms_var.set(c.get("ms", 100))
        self.pos_mode_var.set(c.get("mode", "موقعیت فعلی ماوس"))
        self.x_var.set(c.get("x", 0))
        self.y_var.set(c.get("y", 0))
        self.repeat_var.set(c.get("repeat_mode", "بی‌نهایت"))
        self.repeat_count_var.set(c.get("repeat_count", 100))
        self.hotkey_var.set(c.get("hotkey", "F6"))
        self.sch_h_var.set(c.get("sch_h", 12))
        self.sch_m_var.set(c.get("sch_m", 0))
        self.sch_s_var.set(c.get("sch_s", 0))
        self.sch_ms_var.set(c.get("sch_ms", 0))

    def _collect_config(self) -> dict:
        return {
            "button": self.btn_var.get(),
            "click_type": self.click_type_var.get(),
            "hours": self.h_var.get(),
            "minutes": self.m_var.get(),
            "seconds": self.s_var.get(),
            "ms": self.ms_var.get(),
            "mode": self.pos_mode_var.get(),
            "x": self.x_var.get(),
            "y": self.y_var.get(),
            "repeat_mode": self.repeat_var.get(),
            "repeat_count": self.repeat_count_var.get(),
            "hotkey": self.hotkey_var.get(),
            "work_mode": self.work_mode_var.get(),
            "sch_h": self.sch_h_var.get(),
            "sch_m": self.sch_m_var.get(),
            "sch_s": self.sch_s_var.get(),
            "sch_ms": self.sch_ms_var.get(),
        }

    # ========================================================
    # ساعت زنده
    # ========================================================
    def _tick_clock(self):
        now = iran_now()
        self.clock_label.config(
            text=now.strftime("%H:%M:%S.") + f"{now.microsecond // 1000:03d}"
        )
        try:
            self.date_label.config(
                text=now.strftime("%A %d %B %Y")
            )
        except Exception:
            self.date_label.config(text=now.strftime("%Y-%m-%d"))

        # شمارش معکوس
        if waiting and self._schedule_target is not None:
            diff = self._schedule_target - time.perf_counter()
            if diff > 0:
                h = int(diff // 3600)
                m = int((diff % 3600) // 60)
                s = int(diff % 60)
                ms = int((diff * 1000) % 1000)
                self.countdown_label.config(
                    text=f"⏳ شروع در: {h:02d}:{m:02d}:{s:02d}.{ms:03d}"
                )
            else:
                self.countdown_label.config(text="✅ در حال شروع...")
        else:
            self.countdown_label.config(text="")

        self.root.after(30, self._tick_clock)

    # ========================================================
    # کلید میانبر
    # ========================================================
    def _start_hotkey_listener(self):
        def on_press(key):
            try:
                if key == keyboard.Key.esc:
                    if running or waiting:
                        self.root.after(0, self.stop_clicking)
                    return

                name = self.hotkey_var.get().lower()
                if hasattr(key, "name") and key.name == name:
                    if running or waiting:
                        self.root.after(0, self.stop_clicking)
                    else:
                        self.root.after(0, self.start_clicking)
            except Exception:
                pass

        self.listener = keyboard.Listener(on_press=on_press)
        self.listener.daemon = True
        self.listener.start()

    # ========================================================
    # منطق کلیک
    # ========================================================
    def _get_button(self) -> Button:
        b = self.btn_var.get()
        if b == "چپ":
            return Button.left
        if b == "راست":
            return Button.right
        return Button.middle

    def _get_delay(self) -> float:
        total = (
            self.h_var.get() * 3600
            + self.m_var.get() * 60
            + self.s_var.get()
            + self.ms_var.get() / 1000.0
        )
        return max(total, 0.001)

    # ========================================================
    # شروع / توقف
    # ========================================================
    def start_clicking(self):
        global waiting, wait_stop_flag, stop_flag

        if running or waiting:
            return

        # ذخیره تنظیمات
        self.cfg = self._collect_config()
        save_config(self.cfg)

        if self.work_mode_var.get() == "immediate":
            self._begin_actual_clicking()
        else:
            # حالت زمان‌بندی
            try:
                self._schedule_target = self._compute_schedule_target()
            except Exception as e:
                messagebox.showerror("خطا", f"محاسبه زمان ناموفق:\n{e}")
                return

            waiting = True
            wait_stop_flag = False
            self._set_status("⏰ در انتظار زمان مقرر...", "#e65100")
            self.start_btn.config(state="disabled")
            self.stop_btn.config(state="normal")

            self.waiter_thread = threading.Thread(
                target=self._wait_and_start, daemon=True
            )
            self.waiter_thread.start()

    def _compute_schedule_target(self) -> float:
        """محاسبه زمان دقیق شروع (perf_counter)"""
        h = self.sch_h_var.get()
        m = self.sch_m_var.get()
        s = self.sch_s_var.get()
        ms = self.sch_ms_var.get()

        now_iran = iran_now()
        target_iran = now_iran.replace(
            hour=h, minute=m, second=s, microsecond=ms * 1000
        )
        if target_iran <= now_iran:
            target_iran += timedelta(days=1)

        diff_seconds = (target_iran - now_iran).total_seconds()
        return time.perf_counter() + diff_seconds

    def _wait_and_start(self):
        """حلقه دقیق انتظار - بدون تأخیر"""
        global waiting, wait_stop_flag

        while not wait_stop_flag:
            remaining = self._schedule_target - time.perf_counter()

            if remaining <= 0:
                break

            # خواب تطبیقی: دقیق‌تر نزدیک هدف
            if remaining > 1.0:
                time.sleep(0.05)
            elif remaining > 0.05:
                time.sleep(0.002)
            elif remaining > 0.005:
                time.sleep(0.0005)
            else:
                # بجای sleep از busy-wait خیلی کوتاه استفاده کن
                pass

        if wait_stop_flag:
            return

        waiting = False
        self.root.after(0, self._begin_actual_clicking)

    def _begin_actual_clicking(self):
        global running, stop_flag, click_count

        running = True
        stop_flag = False
        click_count = 0

        self._set_status("▶ در حال کلیک...", "#2e7d32")
        self.count_label.config(text="تعداد کلیک: 0")
        self.start_btn.config(state="disabled")
        self.stop_btn.config(state="normal")

        self.worker_thread = threading.Thread(
            target=self._click_worker, daemon=True
        )
        self.worker_thread.start()

    def _click_worker(self):
        global click_count, stop_flag

        button = self._get_button()
        delay = self._get_delay()
        double_click = self.click_type_var.get() == "دو‌بار"
        manual = self.pos_mode_var.get() == "مختصات دستی"
        x, y = self.x_var.get(), self.y_var.get()
        infinite = self.repeat_var.get() == "بی‌نهایت"
        max_count = -1 if infinite else max(1, self.repeat_count_var.get())

        count = 0
        next_time = time.perf_counter()

        while not stop_flag:
            if manual:
                mouse.position = (x, y)

            mouse.click(button, 1)
            if double_click:
                time.sleep(0.02)
                mouse.click(button, 1)

            count += 1
            click_count = count
            self.root.after(
                0, lambda c=count: self.count_label.config(
                    text=f"تعداد کلیک: {c}"
                )
            )

            if max_count > 0 and count >= max_count:
                break

            # زمان‌بندی دقیق بدون drift
            next_time += delay
            now = time.perf_counter()
            sleep_time = next_time - now

            if sleep_time > 0.002:
                time.sleep(sleep_time - 0.001)
            while time.perf_counter() < next_time:
                if stop_flag:
                    break
                pass

        self.root.after(0, self._on_worker_finished)

    def _on_worker_finished(self):
        global running
        running = False
        self._set_status("✅ پایان یافت", "#1565c0")
        self.start_btn.config(state="normal")
        self.stop_btn.config(state="disabled")
        self.countdown_label.config(text="")

    def stop_clicking(self):
        global running, waiting, stop_flag, wait_stop_flag

        stop_flag = True
        wait_stop_flag = True
        was_active = running or waiting
        running = False
        waiting = False

        if was_active:
            self._set_status("⏹ متوقف شد", "#ef6c00")
        self.start_btn.config(state="normal")
        self.stop_btn.config(state="disabled")
        self.countdown_label.config(text="")

    # ========================================================
    # وضعیت
    # ========================================================
    def _set_status(self, text: str, color: str):
        self.status_label.config(text=text, fg=color)

    # ========================================================
    # بستن برنامه
    # ========================================================
    def _on_close(self):
        global stop_flag, wait_stop_flag
        stop_flag = True
        wait_stop_flag = True

        try:
            self.cfg = self._collect_config()
            save_config(self.cfg)
        except Exception:
            pass

        if self.listener:
            try:
                self.listener.stop()
            except Exception:
                pass

        # آزادسازی دقت ویندوز
        if sys.platform == "win32":
            try:
                ctypes.windll.winmm.timeEndPeriod(1)
            except Exception:
                pass

        self.root.destroy()


# ============================================================
# نقطه ورود
# ============================================================
def main():
    root = tk.Tk()
    app = AutoClicker(root)
    root.mainloop()


if __name__ == "__main__":
    main()
