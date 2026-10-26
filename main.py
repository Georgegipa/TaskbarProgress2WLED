import ctypes
from ctypes import wintypes
import json
import os
import sys
import time
import requests
import uiautomation as auto

# --- Windows API & Virtual Terminal (ANSI) Setup ---
kernel32 = ctypes.windll.kernel32
user32 = ctypes.windll.user32

STD_OUTPUT_HANDLE = -11
ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004

hOut = kernel32.GetStdHandle(STD_OUTPUT_HANDLE)
out_mode = wintypes.DWORD()
if kernel32.GetConsoleMode(hOut, ctypes.byref(out_mode)):
    kernel32.SetConsoleMode(hOut, out_mode.value | ENABLE_VIRTUAL_TERMINAL_PROCESSING)

# --- ANSI Styling Codes ---
RESET = "\033[0m"
BOLD = "\033[1m"
CYAN = "\033[36m"
WHITE = "\033[97m"
GRAY = "\033[90m"

RED = "\033[91m"
YELLOW = "\033[93m"
GREEN = "\033[92m"

# Static Generic Badge
APP_BADGE = f"{BOLD}{CYAN}[TASK PROGRESS]{RESET}"


# --- Config Loader ---
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

def load_config():
    default = {
        "wled_ip": "192.168.1.1",
        "color_active": [0, 255, 0],
        "color_background": [40, 40, 40]
    }
    if not os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "w") as f:
            json.dump(default, f, indent=2)
        return default
    with open(CONFIG_FILE, "r") as f:
        return json.load(f)


# --- WLED Controller ---
class WledController:
    def __init__(self, ip: str, led_count: int, col_active, col_bg):
        self.url = f"http://{ip}/json/state"
        self.led_count = led_count
        self.col_active = col_active
        self.col_bg = col_bg
        self.last_led_count = -1

    def update(self, percent: float):
        # convert the colors to hex strings
        active_hex = ''.join(f"{c:02X}" for c in self.col_active)
        bg_hex = ''.join(f"{c:02X}" for c in self.col_bg)

        payload = {
              "on": True,
              "seg": [
                {
                  "id": 0,
                  "fx": 98,
                  "ix": int(percent),
                  "col": [ active_hex, bg_hex
                  ]
                }
              ]
            }
        try:
            requests.post(self.url, json=payload, timeout=0.3)
        except Exception:
            pass

    def turn_off(self):
        self.last_led_count = -1
        try:
            requests.post(self.url, json={"on": False}, timeout=0.3)
        except Exception:
            pass


# --- Progress Bar Detection ---
def get_progress_info(control):
    rp = control.GetRangeValuePattern()
    if rp:
        span = rp.Maximum - rp.Minimum
        pct = ((rp.Value - rp.Minimum) / span * 100.0) if span > 0 else 0.0
        return pct, rp.Value, rp.Maximum
    vp = control.GetValuePattern()
    if vp:
        val_str = (vp.Value or "").replace("%", "").strip()
        try:
            val = float(val_str)
            return val, val, 100.0
        except ValueError:
            pass
    return None


def find_first_target():
    root = auto.GetRootControl()
    for win in root.GetChildren():
        try:
            hwnd = win.NativeWindowHandle
            if not hwnd or not user32.IsWindowVisible(hwnd):
                continue
            if win.ClassName in ("Progman", "WorkerW", "Shell_TrayWnd", "NotifyIconOverflowWindow"):
                continue

            found_bar = win.ProgressBarControl(searchDepth=6)
            if found_bar.Exists(0.05, 0.05):
                return found_bar
        except Exception:
            continue
    return None


# --- Main Loop ---
def main():
    cfg = load_config()
    wled = WledController(
        ip=cfg.get("wled_ip", "192.168.1.1"),
        led_count=cfg.get("led_count", 30),
        col_active=cfg.get("color_active", [0, 255, 0]),
        col_bg=cfg.get("color_background", [40, 40, 40])
    )

    auto.SetGlobalSearchTimeout(0.1)

    try:
        while True:
            bar_ctrl = find_first_target()
            if not bar_ctrl:
                time.sleep(0.8)
                continue

            while bar_ctrl.Exists(0.1, 0.1):
                info = get_progress_info(bar_ctrl)

                if info:
                    pct, _, _ = info
                    wled.update(pct)

                    # Dynamic color based on progress percentage
                    if pct < 30.0:
                        prog_color = RED
                    elif pct < 70.0:
                        prog_color = YELLOW
                    else:
                        prog_color = GREEN

                    bar_len = 24
                    filled = int((pct / 100.0) * bar_len)
                    fill_str = f"{prog_color}{'█' * filled}{RESET}"
                    empty_str = f"{GRAY}{'░' * (bar_len - filled)}{RESET}"
                    pct_badge = f"{BOLD}{WHITE}{pct:5.1f}%{RESET}"

                    sys.stdout.write(f"\r{APP_BADGE} ▕{fill_str}{empty_str}▏ {pct_badge}")
                else:
                    sys.stdout.write(f"\r{APP_BADGE} {YELLOW}▕ [BUSY / WORKING...] ▏{RESET}")

                sys.stdout.flush()
                time.sleep(0.25)

            # Cleanup display and reset LEDs when bar disappears
            wled.turn_off()
            sys.stdout.write("\r" + " " * 80 + "\r")
            sys.stdout.flush()

    except (KeyboardInterrupt, SystemExit):
        wled.turn_off()
        sys.stdout.write(f"\n{RESET}")
        sys.stdout.flush()


if __name__ == "__main__":
    main()