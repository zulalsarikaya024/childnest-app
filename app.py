import streamlit as st
import firebase_admin
from firebase_admin import credentials, db
import json
import pandas as pd
import plotly.express as px
import datetime

# Sayfa Yapılandırması
st.set_page_config(page_title="ChildNest AI Pro", page_icon="🚨", layout="wide")

# 1. FIREBASE BAĞLANTISI
if not firebase_admin._apps:
    key_dict = json.loads(st.secrets["textkey"])
    cred = credentials.Certificate(key_dict)
    firebase_admin.initialize_app(cred, {
        'databaseURL': "https://childnest-e3bab-default-rtdb.firebaseio.com/"
    })

# --- AI ÖN TEŞHİS FONKSİYONU ---
def ai_on_tehis(ates, ilac, alerji):
    ates = float(ates)
    if ates >= 39.5:
        return "🚨 ACİL DURUM: Çok yüksek ateş! Hemen bir sağlık kuruluşuna başvurun.", "red"
    elif ates >= 38.5:
        return "⚠️ DİKKAT: Yüksek ateş. Sıvı alımını artırın ve doktorunuza danışın.", "orange"
    elif alerji != "Yok" and ates > 37.5:
        return "🔍 ANALİZ: Alerji öyküsü ve hafif ateş. Yakından takip edilmeli.", "blue"
    else:
        return "✅ DURUM STABİL: Veriler normal sınırlar içinde görünüyor.", "green"

st.title("🛡️ ChildNest: AI Destekli Sağlık Takip Sistemi")

# --- ACİL DURUM BUTONU (Üst Panel) ---
if st.button("🚨 ACİL YARDIM ÇAĞRISI (Doktora Bildir)", use_container_width=True):
    st.error("⚠️ Acil durum sinyali doktora iletildi! Lütfen bebeği serin tutun ve tıbbi yardım bekleyin.")
    st.balloons() # Dikkat çekmek için

st.markdown("---")

# --- SOL PANEL: ANNE VE MESAJLAŞMA ---
with st.sidebar:
    st.header("👩‍👦 Anne & İletişim Paneli")
    
    # Veri Giriş Formu
    with st.form("anne_formu", clear_on_submit=True):
        bebek_adi = st.text_input("Bebeğin Adı")
        ates = st.number_input("Ateş (°C)", 35.0, 42.0, 37.0, 0.1)
        boy = st.number_input("Boy (cm)", 30, 150, 50)
        kilo = st.number_input("Kilo (kg)", 1, 50, 6)
        ilac = st.text_input("Verilen İlaç")
        alerji = st.text_input("Alerji (Yoksa boş)")
        
        submit = st.form_submit_button("🩺 Kaydı Gönder")
        
        if submit and bebek_adi:
            ref = db.reference('/Basvurular')
            ref.push({
                'bebek_adi': bebek_adi,
                'ates': ates,
                'boy': boy,
                'kilo': kilo,
                'ilac': ilac if ilac else "Yok",
                'alerji': alerji if alerji else "Yok",
                'zaman': datetime.datetime.now().strftime("%d/%m %H:%M")
            })
            st.success("Veri iletildi.")

    st.divider()
    # 6. ÖZELLİK: CANLI SOHBET (Basit Versiyon)
    st.subheader("💬 Doktorla Sohbet")
    mesaj = st.text_area("Sorunuzu buraya yazın...")
