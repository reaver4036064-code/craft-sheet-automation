"""环境配置：沙箱/正式切换。无依赖。"""
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent

# === Environment mode (sandbox / production) ===
# ★ 唯一区别：mc 后面有无 "two"
#   正式: https://mc.fsjqfz.xyz
#   沙箱: https://mctwo.fsjqfz.xyz
def _load_mode():
    mode_path = SCRIPT_DIR / ".mode"
    if mode_path.exists():
        return mode_path.read_text(encoding="utf-8").strip()
    return "production"  # default safe — 正式系统

_MODE = _load_mode()
_URLS = {
    "sandbox":    {"api": "https://mctwo.fsjqfz.xyz/makeCloth", "web": "https://mctwo.fsjqfz.xyz"},
    "production": {"api": "https://mc.fsjqfz.xyz/makeCloth",    "web": "https://mc.fsjqfz.xyz"},
}
BASE = _URLS[_MODE]["api"]
print(f"[MODE] {_MODE.upper()} → {_URLS[_MODE]['web']}")
