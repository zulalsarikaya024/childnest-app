import streamlit as st
import firebase_admin
from firebase_admin import credentials, db
import json
import pandas as pd
import plotly.express as px
import datetime

# Sayfa Genişliği ve Tema
st.set_page_config(page_title="ChildNest Pro", page_icon="📊", layout="wide")

# 1. FIREBASE BAĞLANTISI
if not firebase_admin._apps:
    key_dict = json.loads(st.secrets["textkey"])
    cred = credentials.Certificate(key_dict)
    firebase_admin.initialize_app(cred, {
        'databaseURL': "https://childnest-e3bab-default-rtdb.firebaseio.com/"
    })

st.title("🏥 ChildNest: Kişiselleştirilmiş Gelişim Paneli")

# --- VERİ ÇEKME ---
ref = db.reference('/Basvurular')
veriler = ref.get()

if veriler:
    df = pd.DataFrame(list(veriler.values()))
    
    # --- ÜST PANEL: ÖZEL AYARLAR ---
    st.subheader("🔍 Bebek Seçimi ve Filtreleme")
    secilen_bebek = st.selectbox("İncelemek istediğiniz bebeği seçin:", df['bebek_adi'].unique())
    
    # Seçilen bebeğe özel veriyi ayıkla
    bebek_df = df[df['bebek_adi'] == secilen_bebek].copy()
    
    # --- GRAFİKLER ---
    col1, col2 = st.columns(2)

    with col1:
        st.markdown(f"### 🌡️ {secilen_bebek} - Ateş Geçmişi")
        fig_ates = px.line(bebek_df, x='zaman', y='ates', markers=True, 
                          color_discrete_sequence=['#ff4b4b'])
        st.plotly_chart(fig_ates, use_container_width=True)

    with col2:
        st.markdown(f"### ⚖️ {secilen_bebek} - Boy & Kilo Trendi")
        fig_gelisim = px.line(bebek_df, x='zaman', y=['boy', 'kilo'], markers=True)
        st.plotly_chart(fig_gelisim, use_container_width=True)

    st.divider()

    # --- DETAYLI LİSTE ---
    st.subheader(f"📋 {secilen_bebek} - Tüm Kayıtlar")
    for i, row in bebek_df.iloc[::-1].iterrows():
        status = "🚨 YÜKSEK" if float(row['ates']) >= 38.5 else "✅ NORMAL"
        with st.expander(f"📅 {row['zaman']} | Ateş: {row['ates']}°C | {status}"):
            c1, c2, c3 = st.columns(3)
            c1.metric("Boy (cm)", f"{row['boy']} cm")
            c2.metric("Kilo (kg)", f"{row['kilo']} kg")
            c3.metric("Ateş", f"{row['ates']} °C")
            
            st.info(f"💊 **İlaç:** {row.get('ilac', 'Yok')} | **Doz:** {row.get('doz', 'Belirtilmedi')} | ⚠️ **Alerji:** {row.get('alerji', 'Yok')}")

else:
    st.info("Henüz veri yok. Lütfen sol taraftaki formu doldurun.")

# --- YENİ VERİ GİRİŞİ (SIDEBAR) ---
with st.sidebar:
    st.header("📥 Yeni Ölçüm Ekle")
    with st.form("yeni_form"):
        y_isim = st.text_input("Bebek Adı")
        y_boy = st.number_input("Boy (cm)", 30, 150, 50)
        y_kilo = st.number_input("Kilo (kg)", 1, 50, 6)
        y_ates = st.number_input("Ateş (°C)", 35.0, 42.0, 37.0)
        y_ilac = st.text_input("İlaç Adı")
        y_doz = st.selectbox("Doz", ["Sabah", "Öğle", "Akşam", "Sabah-Akşam", "Sabah-Öğle-Akşam"])
        y_alerji = st.text_input("Alerji")
        
        if st.form_submit_button("Kaydet"):
            if y_isim:
                ref.push({
                    'bebek_adi': y_isim,
                    'boy': y_boy,
                    'kilo': y_kilo,
                    'ates': y_ates,
                    'ilac': y_ilac if y_ilac else "Yok",
                    'doz': y_doz,
                    'alerji': y_alerji if y_alerji else "Yok",
                    'zaman': datetime.datetime.now().strftime("%d/%m %H:%M")
                })
                st.success("Kayıt eklendi!")
                st.rerun()
