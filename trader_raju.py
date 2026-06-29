import streamlit as st
import threading
import time
import requests
import pyotp
from datetime import datetime, timedelta
from collections import deque

try:
    from SmartApi import SmartConnect
except ImportError:
    st.error("SmartApi not installed. Please install smartapi-python")

# ==============================================================
#  SECTION 1 — CREDENTIALS (तुमची माहिती भरा)
# ==============================================================
API_KEY      = "dC2jWcZV"
CLIENT_ID    = "R292348"
PASSWORD     = "1217"
TOTP_SECRET  = "7LBOZEUFKN6LBWNNGMFPPJSK6Y"

TELEGRAM_BOT_TOKEN = "8840916529:AAGfhCmOUa2rzWDtwmeqFLUytp68Gwv5r88"
TELEGRAM_CHAT_ID   = "8332272265"

# ==============================================================
#  SECTION 2 — GLOBAL CONFIG (८ अटींचे पॅरामीटर्स)
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
        if not prices or len(prices) < period: return 0.0
        k = 2.0 / (period + 1)
        val = sum(prices[:period]) / period
        for p in prices[period:]:
            val = p * k + val * (1 - k)
        return round(val, 2)

    @staticmethod
    def rsi(prices: list, period: int = 14) -> float:
        if not prices or len(prices) < period + 1: return 50.0
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
#  SECTION 4 — TELEGRAM FUNCTIONS
# ==============================================================
def send_telegram_msg(msg):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"}
        requests.post(url, json=payload, timeout=5)
    except:
        pass

# ==============================================================
#  SECTION 5 — SCANNER ENGINE (८ अटींचे लाईव्ह स्कॅनिंग)
# ==============================================================
class ScannerEngine:
    def _init_(self, api_instance):  # हा भाग फिक्स केला
        self.smart = api_instance
        self.active = False
        self._c5 = deque(maxlen=100); self._h5 = deque(maxlen=100)
        self._l5 = deque(maxlen=100); self._v5 = deque(maxlen=100)
        self._c15 = deque(maxlen=60)
        self.last_signal = None

    def start(self):
        self.active = True
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        send_telegram_msg("🎯 राजू भाऊ, क्लाउड इंजिन तुमच्या ८ अटींच्या महा-स्ट्रॅटेजीसह यशस्वीरित्या सुरू झालं आहे!\n\nऑप्शन चेन + फिबोनॅची + चार्ट पॅटर्न्स स्कॅनिंग बॅकग्राउंडला २४ तास कार्यरत झाले आहे.")
        
        while self.active:
            try:
                now = datetime.now()
                in_win = any(start <= now.strftime("%H:%M") <= end for start, end in [("09:30", "11:30"), ("13:30", "15:15")])
                
                ltp_resp = self.smart.ltpData(EXCHANGE_NSE, "", NIFTY_TOKEN)
                ltp = float(ltp_resp["data"]["ltp"]) if ltp_resp and "data" in ltp_resp and ltp_resp["data"] else 0.0
                
                if ltp == 0.0:
                    time.sleep(REFRESH_SEC)
                    continue

                days_to_thu = (3 - now.weekday()) % 7
                expiry = (now + timedelta(days=days_to_thu)).strftime("%d%b%Y").upper()
                
                url = "https://apiconnect.angelbroking.com/rest/secure/angelbroking/marketData/v1/optionChain"
                headers = {"Authorization": f"Bearer {self.smart.jwtToken}", "Content-Type": "application/json", "X-UserType": "USER", "X-SourceID": "WEB"}
                payload = {"name": NIFTY_SYMBOL, "expirydate": expiry}
                oc_resp = requests.post(url, headers=headers, json=payload, timeout=5).json()
                chain = oc_resp.get("data", [])
                
                total_c = sum(row.get("CE", {}).get("openInterest", 0) for row in chain)
                total_p = sum(row.get("PE", {}).get("openInterest", 0) for row in chain)
                pcr_val = round(total_p / total_c, 3) if total_c > 0 else 1.0
                pcr_trend = "bullish" if pcr_val > PCR_BULL else "bearish" if pcr_val < PCR_BEAR else "sideways"

                start_str = now.replace(hour=9, minute=15, second=0).strftime("%Y-%m-%d %H:%M")
                now_str = now.strftime("%Y-%m-%d %H:%M")
                
                c5m_resp = self.smart.getCandleData({"exchange": EXCHANGE_NSE, "symboltoken": NIFTY_TOKEN, "interval": "FIVE_MINUTE", "fromdate": start_str, "todate": now_str})
                c15m_resp = self.smart.getCandleData({"exchange": EXCHANGE_NSE, "symboltoken": NIFTY_TOKEN, "interval": "FIFTEEN_MINUTE", "fromdate": start_str, "todate": now_str})

                c5m = c5m_resp.get("data", []) if c5m_resp else []
                c15m = c15m_resp.get("data", []) if c15m_resp else []

                if len(c5m) < EMA_PERIOD:
                    time.sleep(REFRESH_SEC)
                    continue

                self._c5.clear(); self._h5.clear(); self._l5.clear(); self._v5.clear(); self._c15.clear()
                for c in c5m:
                    self._c5.append(float(c[4])); self._h5.append(float(c[2]))
                    self._l5.append(float(c[3])); self._v5.append(float(c[5]))
                for c in c15m:
                    self._c15.append(float(c[4]))

                closes5, highs5, lows5, vols5, closes15 = list(self._c5), list(self._h5), list(self._l5), list(self._v5), list(self._c15)

                ema20 = TAEngine.ema(closes5, EMA_PERIOD)
                rsi = TAEngine.rsi(closes5, RSI_PERIOD)
                
                t15 = "neutral"
                if len(closes15) >= 2:
                    t15 = "positive" if (closes15[-1] - closes15[-2]) > 0 else "negative"

                cur_vol = vols5[-1] if vols5 else 0
                high_vol = TAEngine.high_volume(vols5[:-1], cur_vol)

                sh, sl = max(highs5), min(lows5)
                fibs = TAEngine.fibonacci(sh, sl)
                
                at618 = abs(ltp - fibs["0.618"]) / ltp < 0.002
                at50 = abs(ltp - fibs["0.500"]) / ltp < 0.002
                at_fib = at618 or at50
                fib_lbl = "0.618 Golden Pocket" if at618 else "0.500 Mid"

                patt = TAEngine.pattern_bullish(closes5, lows5) if pcr_trend == "bullish" else TAEngine.pattern_bearish(closes5, highs5)

                sig = None
                if pcr_trend == "bullish" and in_win and t15 == "positive" and at_fib and patt and ltp > ema20 and high_vol and rsi > RSI_BULL:
                    sig = f"🟢 BUY CALL (CE)\n🎯 LTP: {ltp}\n📈 Pattern: {patt}\n🔱 Fib: {fib_lbl}\n📊 RSI: {rsi}\n🛡️ SL: Below 20 EMA ({ema20})"
                elif pcr_trend == "bearish" and in_win and t15 == "negative" and at_fib and patt and ltp < ema20 and high_vol and rsi < RSI_BEAR:
                    sig = f"🔴 BUY PUT (PE)\n🎯 LTP: {ltp}\n📉 Pattern: {patt}\n🔱 Fib: {fib_lbl}\n📊 RSI: {rsi}\n🛡️ SL: Above Candle High"

                if sig and sig != self.last_signal:
                    self.last_signal = sig
                    send_telegram_msg(f"🚨 NEW 8-CONFLUENCE SIGNAL 🚨\n\n{sig}\n\n_सर्व ८ अटी मॅच झाल्या आहेत!_")

            except:
                pass
            time.sleep(REFRESH_SEC)

# ==============================================================
#  SECTION 6 — STREAMLIT UI
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
        try:
            totp = pyotp.TOTP(TOTP_SECRET).now()
            smart = SmartConnect(api_key=API_KEY)
            data = smart.generateSession(CLIENT_ID, PASSWORD, totp)
            
            if data["status"]:
                st.success("✅ Engine Started! Connection Successful with Angel One.")
                st.info("🔄 Scanning Market Conditions... Dashboard is now Running 24/7 on Cloud.")
                
                # फिक्स केलेले इंजिन इनिशिएलायझेशन
                scanner = ScannerEngine(smart)
                scanner.start()
                st.session_state.engine_running = True
            else:
                st.error(f"❌ Angel One Login Failed: {data.get('message', 'Wrong Credentials')}")
        except Exception as e:
            st.error(f"❌ सिस्टीम एरर: {str(e)}")
    else:
        st.warning("⚡ Engine is already running!")

if st.session_state.engine_running:
    st.markdown("### 🟢 System Status: *ACTIVE & RUNNING*")
    st.write("डॅशबोर्ड बॅकग्राउंडला सुरक्षित सुरू झाला आहे. ८ अटींचे स्कॅनर सुरू झाले आहे!")
