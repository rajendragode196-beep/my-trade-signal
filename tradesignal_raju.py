"""
============================================================
  TradeSignal Pro — Live Trading Scanner & Alert App
  Angel One SmartAPI | Nifty & Bank Nifty | Options Chain
============================================================
  Install:
    pip install kivy smartapi-python pyotp requests playsound

  Android (Buildozer buildozer.spec):
    requirements = python3,kivy,requests,pyotp,playsound,smartapi-python
    android.permissions = INTERNET,VIBRATE

  Replace API_KEY, CLIENT_ID, PASSWORD, TOTP_SECRET below.
============================================================
"""

# ── Standard Library ──────────────────────────────────────────
import threading
import time
import math
import json
import os
from datetime import datetime, timedelta
from collections import deque

# ── Angel One SmartAPI ────────────────────────────────────────
try:
    from SmartApi import SmartConnect
    import pyotp
    SMARTAPI_AVAILABLE = True
except ImportError:
    SMARTAPI_AVAILABLE = False
    print("[WARN] smartapi-python not installed. Running in DEMO mode.")

# ── HTTP ──────────────────────────────────────────────────────
import requests

# ── Audio ─────────────────────────────────────────────────────
try:
    from playsound import playsound
    SOUND_AVAILABLE = True
except ImportError:
    SOUND_AVAILABLE = False

# ── Kivy ──────────────────────────────────────────────────────
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.widget import Widget
from kivy.graphics import Color, RoundedRectangle, Ellipse
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.animation import Animation
from kivy.metrics import dp, sp

Window.size = (420, 860)
Window.clearcolor = (0.039, 0.055, 0.102, 1)  # #0A0E1A


# ==============================================================
#  SECTION 1 — CREDENTIALS  (REPLACE BEFORE USE)
# ==============================================================
API_KEY      = "dC2jWcZV"
CLIENT_ID    = "R292348"
PASSWORD     = "1217"
TOTP_SECRET  = "7LBOZEUFKN6LBWNNGMFPPJSK6Y"


# ==============================================================
#  SECTION 2 — GLOBAL CONFIG
# ==============================================================
NIFTY_SYMBOL     = "NIFTY"
BANKNIFTY_SYMBOL = "BANKNIFTY"
NIFTY_TOKEN      = "26000"
BANKNIFTY_TOKEN  = "26009"
EXCHANGE_NSE     = "NSE"
EXCHANGE_NFO     = "NFO"

PCR_BULL  = 1.2
PCR_BEAR  = 0.8
RSI_BULL  = 60
RSI_BEAR  = 40
EMA_PERIOD       = 20
RSI_PERIOD       = 14
VOL_MULTIPLIER   = 1.5
REFRESH_SEC      = 5
OI_REFRESH_SEC   = 30
PCR_LOCK_TIME    = "09:45"

SIGNAL_WINDOWS = [("09:30", "11:30"), ("13:30", "15:15")]

# Colours (hex strings)
C_BG    = "#0A0E1A"
C_CARD  = "#0F1626"
C_BDR   = "#1E2A3A"
C_GREEN = "#00E676"
C_RED   = "#FF5252"
C_AMBER = "#FFB300"
C_BLUE  = "#4FC3F7"
C_DIM   = "#8892A4"
C_WHITE = "#E0E6F0"


# ==============================================================
#  SECTION 3 — COLOUR HELPER
# ==============================================================
def hx(h: str, a: float = 1.0):
    """Hex string → Kivy RGBA tuple."""
    h = h.lstrip("#")
    r, g, b = (int(h[i:i+2], 16) / 255 for i in (0, 2, 4))
    return (r, g, b, a)


# ==============================================================
#  SECTION 4 — TECHNICAL ANALYSIS ENGINE
# ==============================================================
class TAEngine:

    # ── EMA ──────────────────────────────────────────────────
    @staticmethod
    def ema(prices: list, period: int) -> float:
        if not prices:
            return 0.0
        if len(prices) < period:
            return round(sum(prices) / len(prices), 2)
        k = 2.0 / (period + 1)
        val = sum(prices[:period]) / period
        for p in prices[period:]:
            val = p * k + val * (1 - k)
        return round(val, 2)

    # ── RSI (Wilder) ─────────────────────────────────────────
    @staticmethod
    def rsi(prices: list, period: int = 14) -> float:
        if len(prices) < period + 1:
            return 50.0
        gains, losses = [], []
        for i in range(1, len(prices)):
            d = prices[i] - prices[i - 1]
            gains.append(max(d, 0))
            losses.append(max(-d, 0))
        ag = sum(gains[:period]) / period
        al = sum(losses[:period]) / period
        for i in range(period, len(gains)):
            ag = (ag * (period - 1) + gains[i]) / period
            al = (al * (period - 1) + losses[i]) / period
        if al == 0:
            return 100.0
        return round(100 - (100 / (1 + ag / al)), 2)

    # ── Fibonacci ─────────────────────────────────────────────
    @staticmethod
    def fibonacci(high: float, low: float) -> dict:
        r = high - low
        return {
            "high" : round(high, 2),
            "low"  : round(low, 2),
            "0.236": round(high - 0.236 * r, 2),
            "0.382": round(high - 0.382 * r, 2),
            "0.500": round(high - 0.500 * r, 2),
            "0.618": round(high - 0.618 * r, 2),
            "0.786": round(high - 0.786 * r, 2),
        }

    # ── Volume ────────────────────────────────────────────────
    @staticmethod
    def high_volume(history: list, current: float,
                    mult: float = VOL_MULTIPLIER) -> bool:
        if not history:
            return False
        avg = sum(history) / len(history)
        return current > avg * mult if avg > 0 else False

    # ── Bullish patterns (Double Bottom / Rectangle / Pennant)
    @staticmethod
    def pattern_bullish(closes: list, lows: list) -> str:
        if len(closes) < 10 or len(lows) < 10:
            return ""
        # Double Bottom: two lows within 0.3 %, higher close after
        l1 = min(lows[:5])
        l2 = min(lows[5:10])
        if abs(l1 - l2) / max(l1, 0.01) < 0.003:
            if closes[-1] > min(closes[-4:-1]):
                return "Double Bottom (W)"
        # Bullish Rectangle: last 5 closes range < 0.5 %
        hi = max(closes[-5:])
        lo = min(closes[-5:])
        if hi > 0 and (hi - lo) / hi < 0.005:
            return "Bullish Rectangle"
        # Pennant: progressively lower highs but holding support
        recent = closes[-6:]
        if len(recent) >= 4:
            diffs = [recent[i+1] - recent[i] for i in range(len(recent)-1)]
            if all(d > -0.5 for d in diffs) and sum(diffs) < 0:
                return "Bullish Pennant"
        return ""

    # ── Bearish patterns (Double Top / H&S / Rectangle) ──────
    @staticmethod
    def pattern_bearish(closes: list, highs: list) -> str:
        if len(closes) < 10 or len(highs) < 10:
            return ""
        # Double Top
        h1 = max(highs[:5])
        h2 = max(highs[5:10])
        if abs(h1 - h2) / max(h1, 0.01) < 0.003:
            if closes[-1] < max(closes[-4:-1]):
                return "Double Top (M)"
        # Head & Shoulders (3-peak heuristic)
        if len(highs) >= 9:
            lp = max(highs[:3])
            hp = max(highs[3:6])
            rp = max(highs[6:9])
            if hp > lp and hp > rp and abs(lp - rp) / max(hp, 0.01) < 0.015:
                return "Head & Shoulders"
        # Bearish Rectangle
        hi = max(closes[-5:])
        lo = min(closes[-5:])
        if hi > 0 and (hi - lo) / hi < 0.005:
            return "Bearish Rectangle"
        return ""


# ==============================================================
#  SECTION 5 — ANGEL ONE API WRAPPER
# ==============================================================
class AngelOneAPI:

    def __init__(self):
        self.smart      = None
        self.auth_token = None
        self.connected  = False
        self.demo_mode  = False
        # Demo base prices
        self._dltp = {NIFTY_TOKEN: 24812.5, BANKNIFTY_TOKEN: 52340.75}

    # ── Login ─────────────────────────────────────────────────
    def login(self) -> bool:
        if not SMARTAPI_AVAILABLE or API_KEY == "YOUR_API_KEY_HERE":
            print("[API] Demo mode active.")
            return False
        try:
            totp = pyotp.TOTP(TOTP_SECRET).now()
            self.smart = SmartConnect(api_key=API_KEY)
            data = self.smart.generateSession(CLIENT_ID, PASSWORD, totp)
            if data["status"]:
                self.auth_token = data["data"]["jwtToken"]
                self.connected  = True
                self.demo_mode  = False
                print("[API] Logged in to Angel One.")
                return True
            print(f"[API] Login failed: {data}")
            return False
        except Exception as e:
            print(f"[API] Login error: {e}")
            return False

    # ── LTP ───────────────────────────────────────────────────
    def get_ltp(self, token: str,
                exchange: str = EXCHANGE_NSE) -> float:
        if self.demo_mode:
            import random
            drift = random.uniform(-0.8, 0.8)
            self._dltp[token] = round(self._dltp[token] + drift, 2)
            return self._dltp[token]
        try:
            r = self.smart.ltpData(exchange, "", token)
            return float(r["data"]["ltp"])
        except Exception as e:
            print(f"[API] LTP error: {e}")
            return 0.0

    # ── Option Chain ──────────────────────────────────────────
    def get_option_chain(self, symbol: str, expiry: str) -> dict:
        if self.demo_mode:
            return self._demo_oc(symbol)
        try:
            url = ("https://apiconnect.angelbroking.com/rest/secure/"
                   "angelbroking/marketData/v1/optionChain")
            headers = {
                "Authorization": f"Bearer {self.auth_token}",
                "Content-Type" : "application/json",
                "Accept"       : "application/json",
                "X-UserType"   : "USER",
                "X-SourceID"   : "WEB",
            }
            payload = {"name": symbol, "expirydate": expiry}
            r = requests.post(url, headers=headers,
                              data=json.dumps(payload), timeout=10)
            return self._parse_oc(r.json().get("data", []))
        except Exception as e:
            print(f"[API] OC error: {e}")
            return self._demo_oc(symbol)

    def _parse_oc(self, chain: list) -> dict:
        call_oi, put_oi, call_chg, put_chg = {}, {}, {}, {}
        total_c = total_p = 0
        for row in chain:
            s = row.get("strikePrice", 0)
            ce = row.get("CE", {})
            pe = row.get("PE", {})
            call_oi[s]  = ce.get("openInterest", 0)
            put_oi[s]   = pe.get("openInterest", 0)
            call_chg[s] = ce.get("changeinOpenInterest", 0)
            put_chg[s]  = pe.get("changeinOpenInterest", 0)
            total_c += call_oi[s]
            total_p += put_oi[s]
        pcr  = round(total_p / total_c, 3) if total_c > 0 else 1.0
        mcs  = max(call_oi, key=call_oi.get, default=0)
        mps  = max(put_oi,  key=put_oi.get,  default=0)
        return {
            "pcr"               : pcr,
            "max_call_oi_strike": mcs,
            "max_put_oi_strike" : mps,
            "max_call_oi"       : call_oi.get(mcs, 0),
            "max_put_oi"        : put_oi.get(mps, 0),
            "call_buildup"      : ("long"  if call_chg.get(mcs,0) > 0
                                   else "short" if call_chg.get(mcs,0) < 0
                                   else "neutral"),
            "put_buildup"       : ("long"  if put_chg.get(mps,0) > 0
                                   else "short" if put_chg.get(mps,0) < 0
                                   else "neutral"),
        }

    def _demo_oc(self, symbol: str) -> dict:
        import random
        base_pcr = 1.28 if symbol == NIFTY_SYMBOL else 1.15
        pcr = round(base_pcr + random.uniform(-0.07, 0.07), 3)
        if symbol == NIFTY_SYMBOL:
            rs, ss, ro, so = 24900, 24700, 124750, 98240
        else:
            rs, ss, ro, so = 52500, 52000, 214500, 187320
        return {
            "pcr"               : pcr,
            "max_call_oi_strike": rs, "max_put_oi_strike": ss,
            "max_call_oi"       : ro, "max_put_oi"       : so,
            "call_buildup"      : random.choice(["long","short","neutral"]),
            "put_buildup"       : "long",
        }

    # ── Historical candles ────────────────────────────────────
    def get_candles(self, token: str, interval: str,
                    from_dt: str, to_dt: str,
                    exchange: str = EXCHANGE_NSE) -> list:
        if self.demo_mode:
            return self._demo_candles()
        try:
            r = self.smart.getCandleData({
                "exchange"   : exchange,
                "symboltoken": token,
                "interval"   : interval,
                "fromdate"   : from_dt,
                "todate"     : to_dt,
            })
            out = []
            for c in r.get("data", []):
                out.append({
                    "time"  : c[0], "open"  : float(c[1]),
                    "high"  : float(c[2]), "low"   : float(c[3]),
                    "close" : float(c[4]), "volume": float(c[5]),
                })
            return out
        except Exception as e:
            print(f"[API] Candle error: {e}")
            return self._demo_candles()

    def _demo_candles(self) -> list:
        import random
        base = 24800.0
        out  = []
        for _ in range(50):
            o = base + random.uniform(-25, 25)
            h = o + random.uniform(5, 35)
            l = o - random.uniform(5, 35)
            c = random.uniform(l, h)
            out.append({
                "time": "", "open": o, "high": h,
                "low": l,  "close": c,
                "volume": random.randint(50_000, 200_000),
            })
            base = c
        return out


# ==============================================================
#  SECTION 6 — SCANNER ENGINE  (background thread)
# ==============================================================
class ScannerEngine:

    def __init__(self, api: AngelOneAPI):
        self.api    = api
        self.lock   = threading.Lock()
        self.active = False

        # ── Shared state dict ─────────────────────────────────
        self._s = {
            "active_index"       : NIFTY_SYMBOL,
            "active_token"       : NIFTY_TOKEN,
            "ltp"                : 0.0,
            "ltp_change"         : 0.0,
            "ltp_change_pct"     : 0.0,
            "ltp_dir"            : "flat",
            "pcr"                : 1.0,
            "pcr_trend"          : "sideways",
            "pcr_locked"         : False,
            "max_call_oi_strike" : 0,
            "max_put_oi_strike"  : 0,
            "max_call_oi"        : 0,
            "max_put_oi"         : 0,
            "call_buildup"       : "neutral",
            "put_buildup"        : "neutral",
            "swing_high"         : 0.0,
            "swing_low"          : 0.0,
            "fib"                : {},
            "at_fib"             : False,
            "fib_label"          : "",
            "ema20"              : 0.0,
            "rsi"                : 50.0,
            "price_vs_ema"       : "neutral",
            "trend_15"           : "neutral",
            "vol_status"         : "normal",
            "pattern"            : "",
            "in_window"          : False,
            "window_label"       : "PRE-MARKET",
            "current_time"       : "--:--:--",
            "signal"             : None,
            "signal_details"     : {},
            "status_msg"         : "DEMO",
        }

        # ── Ring buffers ──────────────────────────────────────
        self._c5   = deque(maxlen=100)   # 5-min closes
        self._h5   = deque(maxlen=100)   # 5-min highs
        self._l5   = deque(maxlen=100)   # 5-min lows
        self._v5   = deque(maxlen=100)   # 5-min volumes
        self._c15  = deque(maxlen=60)    # 15-min closes
        self._prev = 0.0

    # ── Public API ────────────────────────────────────────────
    def set_index(self, idx: str):
        tok = NIFTY_TOKEN if idx == NIFTY_SYMBOL else BANKNIFTY_TOKEN
        with self.lock:
            self._s["active_index"] = idx
            self._s["active_token"] = tok
            self._s["signal"]       = None
            self._s["pcr_locked"]   = False
        for buf in (self._c5, self._h5, self._l5, self._v5, self._c15):
            buf.clear()

    def state(self) -> dict:
        with self.lock:
            return dict(self._s)

    def start(self):
        self.active = True
        threading.Thread(target=self._loop, daemon=True).start()

    def stop(self):
        self.active = False

    # ── Main loop ─────────────────────────────────────────────
    def _loop(self):
        oi_tick = 0
        while self.active:
            try:
                now   = datetime.now()
                token = self._s["active_token"]
                index = self._s["active_index"]

                # 1. Time window
                in_win, win_lbl = self._time_window(now)

                # 2. LTP
                ltp  = self.api.get_ltp(token)
                prev = self._prev or ltp
                chg  = round(ltp - prev, 2)
                pct  = round(chg / prev * 100, 3) if prev else 0.0
                self._prev = ltp
                ldir = "up" if chg > 0 else "down" if chg < 0 else "flat"

                # 3. Option chain (throttled)
                oi_tick += REFRESH_SEC
                if oi_tick >= OI_REFRESH_SEC:
                    oi_tick = 0
                    expiry  = self._expiry()
                    oi      = self.api.get_option_chain(index, expiry)
                    locked  = self._s["pcr_locked"]
                    if now.strftime("%H:%M") >= PCR_LOCK_TIME and not locked:
                        locked = True
                    pcr_val   = (self._s["pcr"] if locked
                                 else oi["pcr"])
                    pcr_trend = ("bullish"  if pcr_val > PCR_BULL
                                 else "bearish" if pcr_val < PCR_BEAR
                                 else "sideways")
                    with self.lock:
                        self._s.update({
                            "pcr"               : pcr_val,
                            "pcr_trend"         : pcr_trend,
                            "pcr_locked"        : locked,
                            "max_call_oi_strike": oi["max_call_oi_strike"],
                            "max_put_oi_strike" : oi["max_put_oi_strike"],
                            "max_call_oi"       : oi["max_call_oi"],
                            "max_put_oi"        : oi["max_put_oi"],
                            "call_buildup"      : oi["call_buildup"],
                            "put_buildup"       : oi["put_buildup"],
                        })

                # 4. Candle data
                start_str = now.replace(hour=9, minute=15,
                            second=0, microsecond=0
                            ).strftime("%Y-%m-%d %H:%M")
                now_str   = now.strftime("%Y-%m-%d %H:%M")

                c5m  = self.api.get_candles(token, "FIVE_MINUTE",
                                            start_str, now_str)
                c15m = self.api.get_candles(token, "FIFTEEN_MINUTE",
                                            start_str, now_str)

                for c in (c5m or [])[-5:]:
                    self._c5.append(c["close"])
                    self._h5.append(c["high"])
                    self._l5.append(c["low"])
                    self._v5.append(c["volume"])
                for c in (c15m or [])[-3:]:
                    self._c15.append(c["close"])

                closes5  = list(self._c5)
                highs5   = list(self._h5)
                lows5    = list(self._l5)
                vols5    = list(self._v5)
                closes15 = list(self._c15)

                # 5. Indicators
                ema20  = TAEngine.ema(closes5, EMA_PERIOD)
                rsi    = TAEngine.rsi(closes5, RSI_PERIOD)
                pve    = ("above" if ltp > ema20
                          else "below" if ltp < ema20 else "neutral")
                t15    = "neutral"
                if len(closes15) >= 2:
                    slope = closes15[-1] - closes15[-2]
                    t15   = ("positive" if slope > 0
                              else "negative" if slope < 0 else "neutral")

                cur_vol    = vols5[-1] if vols5 else 0
                is_high_v  = TAEngine.high_volume(vols5[:-1], cur_vol)
                vol_status = "high" if is_high_v else "normal"

                # 6. Fibonacci
                sh   = max(highs5) if highs5 else ltp
                sl   = min(lows5)  if lows5  else ltp
                fibs = TAEngine.fibonacci(sh, sl)
                at618 = abs(ltp - fibs["0.618"]) / max(ltp, 0.01) < 0.002
                at50  = abs(ltp - fibs["0.500"]) / max(ltp, 0.01) < 0.002
                at_fib = at618 or at50
                fib_lbl = ("Near 0.618 Golden Pocket" if at618
                            else "Near 0.500 Mid" if at50 else "")

                # 7. Chart pattern
                pt    = self._s.get("pcr_trend", "sideways")
                patt  = ""
                if pt == "bullish":
                    patt = TAEngine.pattern_bullish(closes5, lows5)
                elif pt == "bearish":
                    patt = TAEngine.pattern_bearish(closes5, highs5)

                # 8. Signal evaluation
                sig, sig_d = self._evaluate(
                    pt, ltp, ema20, rsi, at_fib, fib_lbl,
                    t15, is_high_v, patt, in_win)

                # 9. Write state
                with self.lock:
                    s = self._s
                    s["ltp"]            = ltp
                    s["ltp_change"]     = chg
                    s["ltp_change_pct"] = pct
                    s["ltp_dir"]        = ldir
                    s["ema20"]          = ema20
                    s["rsi"]            = rsi
                    s["price_vs_ema"]   = pve
                    s["trend_15"]       = t15
                    s["vol_status"]     = vol_status
                    s["pattern"]        = patt
                    s["swing_high"]     = round(sh, 2)
                    s["swing_low"]      = round(sl, 2)
                    s["fib"]            = fibs
                    s["at_fib"]         = at_fib
                    s["fib_label"]      = fib_lbl
                    s["in_window"]      = in_win
                    s["window_label"]   = win_lbl
                    s["current_time"]   = now.strftime("%H:%M:%S")
                    s["status_msg"]     = ("DEMO" if self.api.demo_mode
                                           else "LIVE")
                    if sig:
                        s["signal"]         = sig
                        s["signal_details"] = sig_d

            except Exception as e:
                print(f"[Scanner] Error: {e}")

            time.sleep(REFRESH_SEC)

    # ── Signal evaluator ──────────────────────────────────────
    def _evaluate(self, pcr_trend, ltp, ema20, rsi,
                  at_fib, fib_lbl, t15, high_vol,
                  pattern, in_win):
        if pcr_trend == "sideways" or not in_win:
            return None, {}

        if pcr_trend == "bullish":
            conds = {
                "PCR > 1.2 (Bullish)"             : True,
                "Active Time Window"               : in_win,
                "15-min Trend Positive"            : t15 == "positive",
                f"Price at Fib Zone ({fib_lbl})"  : at_fib,
                f"Bullish Pattern ({pattern})"     : bool(pattern),
                "5-min Close Above 20 EMA"         : ltp > ema20,
                "High Volume Confirmation"         : high_vol,
                f"RSI > {RSI_BULL}"                : rsi > RSI_BULL,
            }
            if all(conds.values()):
                return "call", {
                    "type"    : "BUY CALL (CE)",
                    "conds"   : conds,
                    "sl"      : f"Below 20 EMA / Pattern Low ({ema20:,.2f})",
                    "ltp"     : ltp,
                    "rsi"     : rsi,
                    "pattern" : pattern,
                    "fib"     : fib_lbl,
                    "time"    : datetime.now().strftime("%H:%M:%S"),
                }

        elif pcr_trend == "bearish":
            conds = {
                "PCR < 0.8 (Bearish)"              : True,
                "Active Time Window"                : in_win,
                "15-min Trend Negative"             : t15 == "negative",
                f"Price at Fib Zone ({fib_lbl})"   : at_fib,
                f"Bearish Pattern ({pattern})"      : bool(pattern),
                "5-min Close Below 20 EMA"          : ltp < ema20,
                "High Volume Confirmation"          : high_vol,
                f"RSI < {RSI_BEAR}"                 : rsi < RSI_BEAR,
            }
            if all(conds.values()):
                return "put", {
                    "type"    : "BUY PUT (PE)",
                    "conds"   : conds,
                    "sl"      : "Above Candle High / Pattern Top",
                    "ltp"     : ltp,
                    "rsi"     : rsi,
                    "pattern" : pattern,
                    "fib"     : fib_lbl,
                    "time"    : datetime.now().strftime("%H:%M:%S"),
                }
        return None, {}

    # ── Time window ───────────────────────────────────────────
    @staticmethod
    def _time_window(now: datetime):
        t = now.strftime("%H:%M")
        for start, end in SIGNAL_WINDOWS:
            if start <= t <= end:
                sess = "MORNING" if start < "12:00" else "AFTERNOON"
                return True, f"ACTIVE — {sess} ({start}–{end})"
        if "11:30" <= t < "13:30":
            return False, "DEAD ZONE — NO SIGNALS (11:30–13:30)"
        if t < "09:30":
            return False, "PRE-MARKET"
        return False, "MARKET CLOSED"

    # ── Nearest Thursday expiry ───────────────────────────────
    @staticmethod
    def _expiry() -> str:
        d = datetime.today()
        days = (3 - d.weekday()) % 7
        return (d + timedelta(days=days)).strftime("%d%b%Y").upper()


# ==============================================================
#  SECTION 7 — KIVY UI WIDGETS
# ==============================================================

class Card(Widget):
    """Rounded rectangle background widget."""

    def __init__(self, bg=C_CARD, border=C_BDR, r=dp(10), **kw):
        super().__init__(**kw)
        self._bg  = bg
        self._bdr = border
        self._r   = r
        self.bind(pos=self._draw, size=self._draw)

    def _draw(self, *_):
        self.canvas.before.clear()
        with self.canvas.before:
            Color(*hx(self._bdr))
            RoundedRectangle(pos=self.pos, size=self.size,
                             radius=[self._r])
            Color(*hx(self._bg))
            RoundedRectangle(
                pos=(self.x + dp(1), self.y + dp(1)),
                size=(self.width - dp(2), self.height - dp(2)),
                radius=[self._r])

    def set_bg(self, color: str):
        self._bg = color
        self._draw()


class SLabel(Label):
    """Styled label with sensible defaults."""

    def __init__(self, text="", size=sp(13), color=C_WHITE,
                 bold=False, align="left", **kw):
        super().__init__(
            text=text, font_size=size,
            color=hx(color), bold=bold,
            halign=align, valign="middle", **kw)
        self.bind(size=lambda *_:
                  setattr(self, "text_size", self.size))


class CondRow(BoxLayout):
    """One condition row: coloured dot + label."""

    def __init__(self, label: str, **kw):
        super().__init__(orientation="horizontal",
                         size_hint_y=None, height=dp(26),
                         spacing=dp(8), **kw)
        self._dot = Widget(size_hint=(None, None),
                           size=(dp(10), dp(10)))
        self.add_widget(self._dot)
        self._lbl = SLabel(text=label, size=sp(11), color=C_DIM)
        self.add_widget(self._lbl)
        self._set(False)

    def _set(self, met: bool):
        c = C_GREEN if met else C_BDR
        self._lbl.color = hx(C_WHITE if met else C_DIM)
        self._dot.canvas.clear()
        with self._dot.canvas:
            Color(*hx(c))
            Ellipse(pos=(self._dot.x, self._dot.y + dp(1)),
                    size=(dp(10), dp(10)))

    def update(self, met: bool, text: str = ""):
        if text:
            self._lbl.text = text
        self._set(met)
        # Redraw dot at correct position
        self._dot.canvas.clear()
        with self._dot.canvas:
            Color(*hx(C_GREEN if met else C_BDR))
            Ellipse(pos=(self._dot.x, self._dot.y + dp(1)),
                    size=(dp(10), dp(10)))


# ==============================================================
#  SECTION 8 — MAIN UI LAYOUT
# ==============================================================

class TradeUI(BoxLayout):

    def __init__(self, engine: ScannerEngine, **kw):
        super().__init__(orientation="vertical",
                         spacing=dp(6), padding=dp(8), **kw)
        self.engine        = engine
        self._last_signal  = None
        self._build()
        Clock.schedule_interval(self._refresh, REFRESH_SEC)
        Clock.schedule_interval(self._tick,    1)

    # ── Build ──────────────────────────────────────────────────
    def _build(self):
        self._topbar()
        self._index_row()
        self._ltp_pcr_row()
        self._time_bar()
        self._oi_row()
        self._fib_block()
        self._tech_row()
        self._cond_block()
        self._alert_block()

    # ── Top bar ────────────────────────────────────────────────
    def _topbar(self):
        bar = BoxLayout(orientation="horizontal",
                        size_hint_y=None, height=dp(38))
        bar.add_widget(SLabel(text="TradeSignal Pro",
                              size=sp(17), bold=True))
        self._conn_lbl = SLabel(text="● DEMO", size=sp(10),
                                color=C_AMBER, align="right",
                                size_hint_x=0.35)
        bar.add_widget(self._conn_lbl)
        self.add_widget(bar)

    # ── Index selector ─────────────────────────────────────────
    def _index_row(self):
        row = BoxLayout(orientation="horizontal",
                        size_hint_y=None, height=dp(36),
                        spacing=dp(8))
        self._b_nifty = Button(
            text="NIFTY 50", font_size=sp(11), bold=True,
            background_color=hx(C_BLUE), color=hx(C_BG))
        self._b_bank  = Button(
            text="BANK NIFTY", font_size=sp(11),
            background_color=hx(C_BDR), color=hx(C_WHITE))
        self._b_nifty.bind(on_press=lambda _:
                           self._sel(NIFTY_SYMBOL))
        self._b_bank.bind(on_press=lambda _:
                          self._sel(BANKNIFTY_SYMBOL))
        row.add_widget(self._b_nifty)
        row.add_widget(self._b_bank)
        self.add_widget(row)

    def _sel(self, idx: str):
        self.engine.set_index(idx)
        self._last_signal  = None
        self._alert_lbl.text  = ""
        self._sl_lbl.text     = ""
        self._at_lbl.text     = ""
        self._silent_lbl.opacity = 1
        self._alert_card.set_bg(C_CARD)
        on, off = hx(C_BLUE), hx(C_BDR)
        if idx == NIFTY_SYMBOL:
            self._b_nifty.background_color = on
            self._b_nifty.color = hx(C_BG)
            self._b_bank.background_color  = off
            self._b_bank.color  = hx(C_WHITE)
        else:
            self._b_bank.background_color  = on
            self._b_bank.color  = hx(C_BG)
            self._b_nifty.background_color = off
            self._b_nifty.color = hx(C_WHITE)

    # ── LTP + PCR ──────────────────────────────────────────────
    def _ltp_pcr_row(self):
        row = BoxLayout(orientation="horizontal",
                        size_hint_y=None, height=dp(82),
                        spacing=dp(8))
        # LTP
        self._ltp_card = Card()
        li = BoxLayout(orientation="vertical", padding=dp(10))
        self._ltp_idx  = SLabel(text="NIFTY 50", size=sp(10), color=C_DIM)
        self._ltp_val  = SLabel(text="--", size=sp(22), bold=True)
        self._ltp_chg  = SLabel(text="", size=sp(11), color=C_GREEN)
        li.add_widget(self._ltp_idx)
        li.add_widget(self._ltp_val)
        li.add_widget(self._ltp_chg)
        self._ltp_card.add_widget(li)
        row.add_widget(self._ltp_card)
        # PCR
        self._pcr_card = Card()
        pi = BoxLayout(orientation="vertical", padding=dp(10))
        pi.add_widget(SLabel(text="LIVE PCR", size=sp(10), color=C_DIM))
        self._pcr_val   = SLabel(text="--", size=sp(22), bold=True,
                                  color=C_AMBER)
        self._pcr_trend = SLabel(text="SIDEWAYS", size=sp(11),
                                  color=C_AMBER)
        pi.add_widget(self._pcr_val)
        pi.add_widget(self._pcr_trend)
        self._pcr_card.add_widget(pi)
        row.add_widget(self._pcr_card)
        self.add_widget(row)

    # ── Time bar ───────────────────────────────────────────────
    def _time_bar(self):
        card = Card(r=dp(8))
        card.size_hint_y = None
        card.height      = dp(36)
        row = BoxLayout(orientation="horizontal", padding=[dp(10), 0])
        self._win_lbl  = SLabel(text="PRE-MARKET", size=sp(11),
                                 color=C_AMBER)
        self._clk_lbl  = SLabel(text="--:--:--", size=sp(13),
                                  color=C_BLUE, bold=True, align="right",
                                  size_hint_x=0.38)
        row.add_widget(self._win_lbl)
        row.add_widget(self._clk_lbl)
        card.add_widget(row)
        self.add_widget(card)

    # ── OI levels ──────────────────────────────────────────────
    def _oi_row(self):
        self.add_widget(self._section("INSTITUTIONAL OI LEVELS"))
        row = BoxLayout(orientation="horizontal",
                        size_hint_y=None, height=dp(78),
                        spacing=dp(8))
        # Resistance
        rc = Card(border="#FF525444")
        ri = BoxLayout(orientation="vertical", padding=dp(8))
        ri.add_widget(SLabel(text="MAX CALL OI — RESIST.",
                             size=sp(9), color="#FF8A80"))
        self._res_s   = SLabel(text="--", size=sp(18), bold=True)
        self._res_oi  = SLabel(text="", size=sp(10), color=C_DIM)
        self._res_bu  = SLabel(text="", size=sp(9),  color="#FF8A80")
        ri.add_widget(self._res_s)
        ri.add_widget(self._res_oi)
        ri.add_widget(self._res_bu)
        rc.add_widget(ri); row.add_widget(rc)
        # Support
        sc = Card(border="#00E67644")
        si = BoxLayout(orientation="vertical", padding=dp(8))
        si.add_widget(SLabel(text="MAX PUT OI — SUPPORT",
                             size=sp(9), color=C_GREEN))
        self._sup_s   = SLabel(text="--", size=sp(18), bold=True)
        self._sup_oi  = SLabel(text="", size=sp(10), color=C_DIM)
        self._sup_bu  = SLabel(text="", size=sp(9),  color=C_GREEN)
        si.add_widget(self._sup_s)
        si.add_widget(self._sup_oi)
        si.add_widget(self._sup_bu)
        sc.add_widget(si); row.add_widget(sc)
        self.add_widget(row)

    # ── Fibonacci ──────────────────────────────────────────────
    def _fib_block(self):
        self.add_widget(self._section("FIBONACCI RETRACEMENT"))
        card = Card()
        card.size_hint_y = None
        card.height      = dp(98)
        g = BoxLayout(orientation="vertical",
                      padding=dp(10), spacing=dp(3))
        self._fib_hi,  self._fib_618 = SLabel(text="--", size=sp(11), bold=True, color=C_RED), \
                                        SLabel(text="--", size=sp(11), bold=True, color=C_AMBER)
        self._fib_50,  self._fib_lo  = SLabel(text="--", size=sp(11), bold=True, color=C_BLUE), \
                                        SLabel(text="--", size=sp(11), bold=True, color=C_GREEN)
        rows_data = [
            ("Swing High", self._fib_hi),
            ("0.618 Golden Pocket", self._fib_618),
            ("0.500 Mid Level", self._fib_50),
            ("Swing Low", self._fib_lo),
        ]
        for lbl_txt, val_lbl in rows_data:
            r = BoxLayout(orientation="horizontal",
                          size_hint_y=None, height=dp(18))
            r.add_widget(SLabel(text=lbl_txt, size=sp(10),
                                color=C_DIM, size_hint_x=0.45))
            r.add_widget(val_lbl)
            g.add_widget(r)
        card.add_widget(g)
        self.add_widget(card)

    # ── Technical row ──────────────────────────────────────────
    def _tech_row(self):
        self.add_widget(self._section("TECHNICAL STATUS"))
        row1 = BoxLayout(orientation="horizontal",
                         size_hint_y=None, height=dp(64), spacing=dp(8))
        # RSI card
        rc = Card()
        ri = BoxLayout(orientation="vertical", padding=dp(8))
        ri.add_widget(SLabel(text="RSI (14)", size=sp(9), color=C_DIM))
        self._rsi_val  = SLabel(text="--", size=sp(18), bold=True,
                                 color=C_GREEN)
        self._rsi_stat = SLabel(text="", size=sp(10), color=C_GREEN)
        ri.add_widget(self._rsi_val); ri.add_widget(self._rsi_stat)
        rc.add_widget(ri); row1.add_widget(rc)
        # EMA card
        ec = Card()
        ei = BoxLayout(orientation="vertical", padding=dp(8))
        ei.add_widget(SLabel(text="PRICE vs 20 EMA", size=sp(9),
                             color=C_DIM))
        self._ema_val = SLabel(text="--", size=sp(18), bold=True,
                                color=C_GREEN)
        self._ema_num = SLabel(text="", size=sp(10), color=C_DIM)
        ei.add_widget(self._ema_val); ei.add_widget(self._ema_num)
        ec.add_widget(ei); row1.add_widget(ec)
        self.add_widget(row1)

        row2 = BoxLayout(orientation="horizontal",
                         size_hint_y=None, height=dp(56), spacing=dp(8))
        # 15-min trend
        tc = Card()
        ti = BoxLayout(orientation="vertical", padding=dp(8))
        ti.add_widget(SLabel(text="15-MIN TREND", size=sp(9), color=C_DIM))
        self._t15_val = SLabel(text="--", size=sp(14), bold=True)
        ti.add_widget(self._t15_val); tc.add_widget(ti)
        row2.add_widget(tc)
        # Volume + pattern
        vc = Card()
        vi = BoxLayout(orientation="vertical", padding=dp(8))
        vi.add_widget(SLabel(text="VOLUME / PATTERN", size=sp(9),
                             color=C_DIM))
        self._vol_val = SLabel(text="--", size=sp(13), bold=True)
        self._pat_val = SLabel(text="", size=sp(9), color=C_DIM)
        vi.add_widget(self._vol_val); vi.add_widget(self._pat_val)
        vc.add_widget(vi); row2.add_widget(vc)
        self.add_widget(row2)

    # ── Conditions checklist ───────────────────────────────────
    def _cond_block(self):
        self.add_widget(self._section("SIGNAL CONDITIONS (ALL MUST MATCH)"))
        card = Card()
        card.size_hint_y = None
        card.height      = dp(168)
        inner = BoxLayout(orientation="vertical",
                          padding=dp(10), spacing=dp(2))
        labels = [
            "PCR trend confirmed",
            "Active time window",
            "15-min trend aligned",
            "Price at Fib zone",
            "Chart pattern formed",
            "5-min candle vs 20 EMA",
            "RSI threshold crossed",
        ]
        self._crows = []
        for lbl in labels:
            cr = CondRow(label=lbl)
            inner.add_widget(cr)
            self._crows.append(cr)
        card.add_widget(inner)
        self.add_widget(card)

    # ── Alert panel ────────────────────────────────────────────
    def _alert_block(self):
        self.add_widget(self._section("ALERT PANEL — SILENT UNTIL CONFLUENCE"))
        self._alert_card = Card()
        self._alert_card.size_hint_y = None
        self._alert_card.height      = dp(112)
        inner = BoxLayout(orientation="vertical",
                          padding=dp(12), spacing=dp(4))
        self._silent_lbl = SLabel(
            text=("◉  Scanner active.\n"
                  "All 8 conditions must fire simultaneously."),
            size=sp(11), color=C_DIM, align="center")
        self._alert_lbl  = SLabel(text="", size=sp(13),
                                   color=C_WHITE, align="center", bold=True)
        self._sl_lbl     = SLabel(text="", size=sp(10),
                                   color=C_AMBER, align="center")
        self._at_lbl     = SLabel(text="", size=sp(10),
                                   color=C_DIM, align="right")
        inner.add_widget(self._silent_lbl)
        inner.add_widget(self._alert_lbl)
        inner.add_widget(self._sl_lbl)
        inner.add_widget(self._at_lbl)
        self._alert_card.add_widget(inner)
        self.add_widget(self._alert_card)

    # ── Section divider label ──────────────────────────────────
    @staticmethod
    def _section(text: str) -> SLabel:
        return SLabel(text=text, size=sp(9), color=C_DIM,
                      size_hint_y=None, height=dp(18))

    # ── UI refresh (every REFRESH_SEC via Clock) ───────────────
    def _refresh(self, _dt):
        s = self.engine.state()

        # Connection
        self._conn_lbl.text  = f"● {s['status_msg']}"
        self._conn_lbl.color = hx(C_GREEN if s["status_msg"] == "LIVE"
                                   else C_AMBER)

        # LTP
        self._ltp_idx.text = s["active_index"]
        ltp = s["ltp"]
        self._ltp_val.text = f"{ltp:,.2f}" if ltp else "--"
        chg = s["ltp_change"]; pct = s["ltp_change_pct"]
        arrow = "▲" if chg > 0 else "▼" if chg < 0 else "—"
        cc    = C_GREEN if chg > 0 else C_RED if chg < 0 else C_DIM
        self._ltp_chg.text  = (f"{arrow} {abs(chg):,.2f}"
                                f"  ({abs(pct):.2f}%)")
        self._ltp_chg.color = hx(cc)

        # PCR
        pcr   = s["pcr"]
        trend = s["pcr_trend"]
        pc    = (C_GREEN if trend == "bullish"
                 else C_RED if trend == "bearish" else C_AMBER)
        bg    = ("#0A1A12" if trend == "bullish"
                 else "#1A0A0A" if trend == "bearish" else C_CARD)
        self._pcr_val.text   = f"{pcr:.3f}"
        self._pcr_val.color  = hx(pc)
        self._pcr_trend.text = trend.upper() + (
            " — CE SCAN" if trend == "bullish"
            else " — PE SCAN" if trend == "bearish"
            else " — NO TRADE ZONE")
        self._pcr_trend.color = hx(pc)
        self._pcr_card.set_bg(bg)

        # Time window
        wc = (C_GREEN if s["in_window"]
               else C_RED if "CLOSED" in s["window_label"]
               else C_AMBER)
        self._win_lbl.text  = s["window_label"]
        self._win_lbl.color = hx(wc)

        # OI
        self._res_s.text  = f"{s['max_call_oi_strike']:,}" if s["max_call_oi_strike"] else "--"
        self._sup_s.text  = f"{s['max_put_oi_strike']:,}"  if s["max_put_oi_strike"]  else "--"
        self._res_oi.text = f"OI: {s['max_call_oi']:,} lots"
        self._sup_oi.text = f"OI: {s['max_put_oi']:,} lots"
        bmap = {"long": "LONG BUILDUP ▲", "short": "SHORT BUILDUP ▼",
                "neutral": "NEUTRAL"}
        self._res_bu.text = bmap.get(s["call_buildup"], "")
        self._sup_bu.text = bmap.get(s["put_buildup"], "")

        # Fibonacci
        f = s["fib"]
        if f:
            self._fib_hi.text  = f"{f.get('high',0):,.2f}"
            self._fib_618.text = f"{f.get('0.618',0):,.2f}"
            self._fib_50.text  = f"{f.get('0.500',0):,.2f}"
            self._fib_lo.text  = f"{f.get('low',0):,.2f}"

        # RSI
        rsi = s["rsi"]
        rc  = (C_GREEN if rsi > RSI_BULL
               else C_RED if rsi < RSI_BEAR else C_AMBER)
        self._rsi_val.text   = f"{rsi:.1f}"
        self._rsi_val.color  = hx(rc)
        self._rsi_stat.text  = (f"Above {RSI_BULL} — BULLISH" if rsi > RSI_BULL
                                 else f"Below {RSI_BEAR} — BEARISH" if rsi < RSI_BEAR
                                 else f"Neutral ({RSI_BEAR}–{RSI_BULL})")
        self._rsi_stat.color = hx(rc)

        # EMA
        pve = s["price_vs_ema"]
        ec  = C_GREEN if pve == "above" else C_RED if pve == "below" else C_AMBER
        self._ema_val.text  = pve.upper()
        self._ema_val.color = hx(ec)
        self._ema_num.text  = f"EMA20: {s['ema20']:,.2f}"

        # 15-min trend
        t15 = s["trend_15"]
        tc  = (C_GREEN if t15 == "positive"
               else C_RED if t15 == "negative" else C_AMBER)
        self._t15_val.text  = t15.upper()
        self._t15_val.color = hx(tc)

        # Volume + pattern
        vs = s["vol_status"]
        self._vol_val.text  = vs.upper()
        self._vol_val.color = hx(C_GREEN if vs == "high" else C_DIM)
        self._pat_val.text  = s.get("pattern") or "No pattern detected"
        self._pat_val.color = hx(C_AMBER if s.get("pattern") else C_DIM)

        # Conditions checklist
        rsi_ok = rsi > RSI_BULL or rsi < RSI_BEAR
        states = [
            trend in ("bullish", "bearish"),
            s["in_window"],
            t15 in ("positive", "negative"),
            s["at_fib"],
            bool(s.get("pattern")),
            pve in ("above", "below"),
            rsi_ok,
        ]
        texts = [
            f"PCR: {pcr:.3f} → {trend.capitalize()}",
            s["window_label"][:32],
            f"15-min Trend: {t15.capitalize()}",
            f"Fib Zone: {s['fib_label'] or 'Not reached yet'}",
            f"Pattern: {s.get('pattern') or 'None detected'}",
            f"Price {pve.upper()} EMA20 ({s['ema20']:,.2f})",
            f"RSI: {rsi:.1f}",
        ]
        for i, cr in enumerate(self._crows):
            cr.update(states[i], texts[i])

        # Alert
        sig = s.get("signal")
        if sig and sig != self._last_signal:
            self._last_signal = sig
            self._fire_alert(s)

    def _tick(self, _dt):
        self._clk_lbl.text = self.engine.state().get("current_time", "--:--:--")

    # ── Fire alert ─────────────────────────────────────────────
    def _fire_alert(self, s: dict):
        d      = s["signal_details"]
        is_ce  = s["signal"] == "call"
        bg     = "#0A1A12" if is_ce else "#1A0A0A"
        tc     = C_GREEN   if is_ce else C_RED
        icon   = "▲ " if is_ce else "▼ "
        label  = "BUY CALL (CE)" if is_ce else "BUY PUT (PE)"

        self._silent_lbl.opacity  = 0
        self._alert_card.set_bg(bg)

        patt = d.get("pattern", "Pattern")
        fib  = d.get("fib",     "Fib Zone")
        rsi  = d.get("rsi",     0)
        threshold = f"> {RSI_BULL}" if is_ce else f"< {RSI_BEAR}"

        self._alert_lbl.text  = (
            f"{icon}{label}\n"
            f"OI Data + {fib} + {patt} + RSI {threshold} — All Matched!"
        )
        self._alert_lbl.color = hx(tc)
        self._sl_lbl.text     = f"SL:  {d.get('sl', '')}"
        self._at_lbl.text     = f"Signal at: {d.get('time', '')}"

        anim = (Animation(opacity=0.25, duration=0.45) +
                Animation(opacity=1.0,  duration=0.45))
        anim.repeat = True
        anim.start(self._alert_lbl)

        threading.Thread(target=self._beep, daemon=True).start()

    # ── Audio beep ─────────────────────────────────────────────
    @staticmethod
    def _beep():
        try:
            if SOUND_AVAILABLE:
                beep = os.path.join(os.path.dirname(__file__), "beep.wav")
                if os.path.exists(beep):
                    playsound(beep, block=True)
                    return
            # Terminal bell fallback
            print("\a\a\a", end="", flush=True)
        except Exception as e:
            print(f"[Audio] {e}")


# ==============================================================
#  SECTION 9 — KIVY APP ENTRY POINT
# ==============================================================

class TradeSignalApp(App):
    title = "TradeSignal Pro"

    def build(self):
        self.api    = AngelOneAPI()
        self.engine = ScannerEngine(self.api)
        threading.Thread(target=self.api.login, daemon=True).start()
        self.engine.start()
        root = ScrollView(do_scroll_x=False)
        ui   = TradeUI(engine=self.engine, size_hint=(1, None))
        ui.bind(minimum_height=ui.setter("height"))
        root.add_widget(ui)
        return root

    def on_stop(self):
        self.engine.stop()


# ==============================================================
#  SECTION 10 — RUN
# ==============================================================
if __name__ == "__main__":
    TradeSignalApp().run()
