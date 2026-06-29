import streamlit as st
import pyotp
import requests
import time
from SmartApi import SmartConnect

# Page Setup
st.set_page_config(page_title="Raju Bhau Trade Cloud", layout="centered")
st.title("🚀 Raju Bhau's 24/7 Trade Cloud Dashboard")

# --- तुमच्या डिटेल्स इथे भरा ---
CLIENT_ID = "R292348"
MPIN = "1217"
API_KEY = "dC2jWcZV"
TOTP_KEY = "7LBOZEUFKN6LBWNNGMFPPJSK6Y" 

TELEGRAM_TOKEN = "8840916529:AAGfhCmOUa2rzWDtwmeqFLUytp68Gwv5r88"
TELEGRAM_CHAT_ID = "8332272265"
# ----------------------------------

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Telegram Error: {e}")

st.subheader("📡 System Status")

if st.button("Start 24/7 Cloud Engine"):
    try:
        # Generating TOTP & Connecting Angel One
        totp = pyotp.TOTP(TOTP_KEY).now()
        obj = SmartConnect(api_key=API_KEY)
        data = obj.generateSession(CLIENT_ID, MPIN, totp)
        
        if data['status']:
            st.success("✅ Engine Started! Connection Successful with Angel One.")
            send_telegram_message("🎯 राजू भाऊ, क्लाउड इंजिन सुरू झालं आहे! आता सिग्नल्स थेट इथे मिळतील.")
            
            st.info("🔄 Scanning Market Conditions... Dashboard is now Running 24/7 on Cloud.")
            
        else:
            st.error(f"❌ Connection Failed: {data['message']}")
            
    except Exception as e:
        st.error(f"❌ Error: {str(e)}")
