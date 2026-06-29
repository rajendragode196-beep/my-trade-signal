import streamlit as st
import threading
import time
import json
from datetime import datetime, timedelta
from collections import deque
import requests
import pyotp
try:
    from SmartApi import SmartConnect
except ImportError:
    st.error("SmartApi not installed. Please install smartapi-python")

# ==============================================================
#  SECTION 1 — CREDENTIALS (तुमचे डिटेल्स इथे टाका)
# ==============================================================
API_KEY      = "dC2jWcZV"
CLIENT_ID    = "R292348"
PASSWORD     = "1217"
TOTP_SECRET  = "7LBOZEUFKN6LBWNNGMFPPJSK6Y"

# Telegram Bot Details
TELEGRAM_BOT_TOKEN = "8840916529:AAGfhCmOUa2rzWDtwmeqFLUytp68Gwv5r88"
TELEGRAM_CHAT_ID   = "8332272265"

# ==============================================================
#  SECTION 2 — GLOBAL CONFIG 
# ==============================================================
NIFTY_SYMBOL     = "NIFTY"
NIFTY_TOKEN      = "26000"
EXCHANGE_NSE     = "NSE"
PCR_BULL         = 1.2
PCR_BEAR         = 0.8
RSI_BULL         = 60
RSI_BEAR         = 40
EMA_PERIOD       = 20
RSI_PERIOD       = 14
VOL_MULTIPLIER   = 1.5
REFRESH_SEC      = 5

# ==============================================================
#  SECTION 3 — TECHNICAL ANALYSIS ENGINE
# ==============================================================
class TAEngine:
    @staticmethod
    def ema(prices: list, period: int) -> float:
        if not prices: return 0.0
        if len(prices) < period: return round(sum(prices) / len(prices), 2)
        k = 2.0 / (period + 1)
        val = sum(prices[:period]) / period
        for p in prices[period:]:
            val = p * k + val * (1 - k)
        return round(val, 2)

    @staticmethod
    def rsi(prices: list, period: int = 14) -> float:
        if len(prices) < period + 1: return 50.0
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
        if al == 0: return 100.0
        return round(100 - (100 / (1 + ag / al)), 2)

    @staticmethod
    def fibonacci(high: float, low: float) -> dict:
        r = high - low
        return {
            "high": round(high, 2), "low": round(low, 2),
            "0.500": round(high - 0.500 * r, 2), "0.618": round(high - 0.618 * r, 2),
        }

    @staticmethod
    def high_volume(history: list, current: float, mult: float = VOL_MULTIPLIER) -> bool:
        if not history: return False
        avg = sum(history) / len(history)
        return current > avg * mult if avg > 0 else False

    @staticmethod
    def pattern_bullish(closes: list, lows: list) -> str:
        if len(closes) < 10 or len(lows) < 10: return ""
        l1, l2 = min(lows[:5]), min(lows[5:10])
        if abs(l1 - l2) / max(l1, 0.01) < 0.003 and closes[-1] > min(closes[-4:-1]):
            return "Double Bottom (W)"
        hi, lo = max(closes[-5:]), min(closes[-5:])
        if hi > 0 and (hi - lo) / hi < 0.005: return "Bullish Rectangle"
        return ""

    @staticmethod
    def pattern_bearish(closes: list, highs: list) -> str:
        if len(closes) < 10 or len(highs) < 10: return ""
        h1, h2 = max(highs[:5]), max(highs[5:10])
        if abs(h1 - h2) / max(h1, 0.01) < 0.003 and closes[-1] < max(closes[-4:-1]):
            return "Double Top (M)"
        hi, lo = max(closes[-5:]), min(closes[-5:])
        if hi > 0 and (hi - lo) / hi < 0.005: return "Bearish Rectangle"
        return ""

# ==============================================================
#  SECTION 4 — ANGEL ONE API WRAPPER
# ==============================================================
class AngelOneAPI:
    def _init_(self):
        self.smart = None
        self.auth_token = None
        self.connected = False

    def login(self) -> bool:
        try:
            totp = pyotp.TOTP(TOTP_SECRET).now()
            self.smart = SmartConnect(api_key=API_KEY)
            data = self.smart.generateSession(CLIENT_ID, PASSWORD, totp)
            if data["status"]:
                self.auth_token = data["data"]["jwtToken"]
                self.connected = True
                return True
            return False
        except:
            return False

    def get_ltp(self, token: str, exchange: str = EXCHANGE_NSE) -> float:
        try:
            r = self.smart.ltpData(exchange, "", token)
            return float(r["data"]["ltp"])
        except: return 0.0

    def get_option_chain(self, symbol: str, expiry: str) -> dict:
        try:
            url = "https://apiconnect.angelbroking.com/rest/secure/angelbroking/marketData/v1/optionChain"
            headers = {
                "Authorization": f"Bearer {self.auth_token}",
                "Content-Type": "application/json", "Accept": "application/json",
                "X-UserType": "USER", "X-SourceID": "WEB",
            }
            payload = {"name": symbol, "expirydate": expiry}
            r = requests.post(url, headers=headers, data=json.dumps(payload), timeout=10)
            return self._parse_oc(r.json().get("data", []))
        except: return {"pcr": 1.0}

    def _parse_oc(self, chain: list) -> dict:
        total_c = total_p = 0
        for row in chain:
            total_c += row.get("CE", {}).get("openInterest", 0)
            total_p += row.get("PE", {}).get("openInterest", 0)
        pcr = round(total_p / total_c, 3) if total_c > 0 else 1.0
        return {"pcr": pcr}

    def get_candles(self, token: str, interval: str, from_dt: str, to_dt: str, exchange: str = EXCHANGE_NSE) -> list:
        try:
            r = self.smart.getCandleData({
                "exchange": exchange, "symboltoken": token, "interval": interval,
                "fromdate": from_dt, "todate": to_dt,
            })
            out = []
            for c in r.get("data", []):
                out.append({
                    "open": float(c[1]), "high": float(c[2]), "low": float(c[3]),
                    "close": float(c[4]), "volume": float(c[5]),
                })
            return out
        except: return []

# ==============================================================
#  SECTION 5 — SCANNER & TELEGRAM ALERT ENGINE
# ==============================================================
def send_telegram_msg(msg):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"}
        requests.post(url, json=payload, timeout=5)
    except:
        pass

class ScannerEngine:
    def _init_(self, api_instance):
        self.api = api_instance
        self.active = False
        self._c5 = deque(maxlen=100); self._h5 = deque(maxlen=100)
        self._l5 = deque(maxlen=100); self._v5 = deque(maxlen=100)
        self._c15 = deque(maxlen=60)
        self.last_signal = None

    def start(self):
        self.active = True
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        send_telegram_msg("🎯 राजू भाऊ, क्लाउड इंजिन यशस्वीरित्या सुरू झालं आहे!\nतुमची PCR + Fib + Pattern ही मूळ स्ट्रॅटेजी आता बॅकग्राउंडला २४ तास लाईव्ह स्कॅन करेल.")
        
        while self.active:
            try:
                now = datetime.now()
                # Live Trading Hours Check
                in_win = any(start <= now.strftime("%H:%M") <= end for start, end in [("09:30", "11:30"), ("13:30", "15:15")])
                
                ltp = self.api.get_ltp(NIFTY_TOKEN)
                if ltp == 0.0:
                    time.sleep(REFRESH_SEC)
                    continue

                days_to_thu = (3 - now.weekday()) % 7
                expiry = (now + timedelta(days=days_to_thu)).strftime("%d%b%Y").upper()
                oi = self.api.get_option_chain(NIFTY_SYMBOL, expiry)
                pcr_val = oi["pcr"]
                pcr_trend = "bullish" if pcr_val > PCR_BULL else "bearish" if pcr_val < PCR_BEAR else "sideways"

                start_str = now.replace(hour=9, minute=15, second=0, microsecond=0).strftime("%Y-%m-%d %H:%M")
                now_str = now.strftime("%Y-%m-%d %H:%M")

                c5m = self.api.get_candles(NIFTY_TOKEN, "FIVE_MINUTE", start_str, now_str)
                c15m = self.api.get_candles(NIFTY_TOKEN, "FIFTEEN_MINUTE", start_str, now_str)

                if c5m:
                    for c in c5m[-10:]:
                        self._c5.append(c["close"]); self._h5.append(c["high"])
                        self._l5.append(c["low"]); self._v5.append(c["volume"])
                if c15m:
                    for c in c15m[-5:]:
                        self._c15.append(c["close"])

                closes5, highs5, lows5, vols5, closes15 = list(self._c5), list(self._h5), list(self._l5), list(self._v5), list(self._c15)

                if len(closes5) >= EMA_PERIOD:
                    ema20 = TAEngine.ema(closes5, EMA_PERIOD)
                    rsi = TAEngine.rsi(closes5, RSI_PERIOD)
                    
                    t15 = "neutral"
                    if len(closes15) >= 2:
                        slope = closes15[-1] - closes15[-2]
                        t15 = "positive" if slope > 0 else "negative" if slope < 0 else "neutral"

                    cur_vol = vols5[-1] if vols5 else 0
                    high_vol = TAEngine.high_volume(vols5[:-1], cur_vol)

                    sh = max(highs5) if highs5 else ltp
                    sl = min(lows5) if lows5 else ltp
                    fibs = TAEngine.fibonacci(sh, sl)
                    
                    at618 = abs(ltp - fibs["0.618"]) / max(ltp, 0.01) < 0.002
                    at50 = abs(ltp - fibs["0.500"]) / max(ltp, 0.01) < 0.002
                    at_fib = at618 or at50
                    fib_lbl = "0.618 Golden Pocket" if at618 else "0.500 Mid" if at50 else ""

                    patt = ""
                    if pcr_trend == "bullish": patt = TAEngine.pattern_bullish(closes5, lows5)
                    elif pcr_trend == "bearish": patt = TAEngine.pattern_bearish(closes5, highs5)

                    sig = None
                    if pcr_trend == "bullish" and in_win and t15 == "positive" and at_fib and patt and ltp > ema20 and high_vol and rsi > RSI_BULL:
                        sig = f"🟢 BUY CALL (CE)\nLTP: {ltp}\nPattern: {patt}\nFib: {fib_lbl}\nRSI: {rsi}\nSL: Below 20 EMA ({ema20})"
                    elif pcr_trend == "bearish" and in_win and t15 == "negative" and at_fib and patt and ltp < ema20 and high_vol and rsi < RSI_BEAR:
                        sig = f"🔴 BUY PUT (PE)\nLTP: {ltp}\nPattern: {patt}\nFib: {fib_lbl}\nRSI: {rsi}\nSL: Above Candle High"

                    if sig and sig != self.last_signal:
                        self.last_signal = sig
                        send_telegram_msg(f"🚨 NEW SIGNAL ALERT 🚨\n\n{sig}\n\n_All 8 Confluence Conditions Matched!_")

            except:
                pass
            time.sleep(REFRESH_SEC)

# ==============================================================
#  SECTION 6 — STREAMLIT CLOUD UI
# ==============================================================
st.set_page_config(page_title="Trade Cloud Dashboard", page_icon="🚀")
st.title("🚀 Raju Bhau's 24/7 Trade Cloud Dashboard")
st.markdown("---")

if 'engine_running' not in st.session_state:
    st.session_state.engine_running = False

if st.button("Start 24/7 Cloud Engine", use_container_width=True):
    if API_KEY == "YOUR_ANGEL_API_KEY":
        st.error("⚠️ कृपया कोडमध्ये तुमचे API Keys आणि Telegram Token भरा!")
    elif not st.session_state.engine_running:
        api_obj = AngelOneAPI()
        if api_obj.login():
            st.success("✅ Engine Started! Connection Successful with Angel One.")
            st.info("🔄 Scanning Market Conditions (PCR + Fib + Patterns)... Dashboard is now Running 24/7 on Cloud.")
            
            # Error fixed here: Passing the correct instance
            scanner_obj = ScannerEngine(api_obj)
            scanner_obj.start()
            st.session_state.engine_running = True
        else:
            st.error("❌ Angel One Login Failed. Check your Credentials.")
    else:
        st.warning("⚡ Engine is already running in the background!")

if st.session_state.engine_running:
    st.markdown("### 🟢 System Status: *ACTIVE & SCANNING LIVE*")
    st.write("डॅशबोर्ड बॅकग्राउंडला सुरक्षित सुरू आहे. आता थेट टेलिग्रामवर मेसेज तपासा!")
