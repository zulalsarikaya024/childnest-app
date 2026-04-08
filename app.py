import streamlit as st
import firebase_admin
from firebase_admin import credentials, db
import json
import pandas as pd
import plotly.express as px
import datetime

# Sayfa Ayarları
st.set_page_config(page_title="ChildNest: Anne & Doktor", page_icon="🏥", layout="wide")

# 1. FIREBASE BAĞLANTISI
if not firebase_admin._apps:
    key_dict = json.loads(st.secrets["textkey"])
    cred = credentials.Certificate(key_dict)
    firebase_admin.initialize_app(cred, {
        'databaseURL': "https://childnest-e3bab-default-rtdb.firebaseio.com/"
    })

# --- GİRİŞ EKRANI SEÇİMİ ---
st.sidebar.title("🚪 Giriş Kapısı")
rol = st.sidebar.radio("Lütfen Rolünüzü Seçin:", ["Anne Paneli 👩‍👦", "Doktor Paneli 👨‍⚕️"])

# --- AI ANALİZ FONKSİYONU ---
def ai_analiz(ates):
    if ates >= 39.5: return "🚨 KRİTİK: Çok yüksek ateş, acil müdahale gerekebilir!", "#ff4b4b"
    if ates >= 38.5: return "⚠️ UYARI: Yüksek ateş, doktora danışılmalı.", "#ffa500"
    return "✅ STABİL: Ateş normal sınırlarda.", "#2ecc71"

# ==========================================
# 👩‍👦 ANNE PANELİ
# ==========================================
if rol == "Anne Paneli 👩‍👦":
    st.title("👩‍👦 ChildNest: Anne Giriş Ekranı")
    st.info("Bebeğinizin bilgilerini buraya girerek doktorunuza anlık olarak iletebilirsiniz.")
    
    col1, col2 = st.columns([1, 2])
    
    with col1:
        with st.form("anne_veri_formu"):
            st.subheader("📝 Yeni Kayıt")
            isim = st.text_input("Bebek Adı")
            ates = st.number_input("Ateş (°C)", 35.0, 42.0, 37.0, 0.1)
            boy = st.number_input("Boy (cm)", 30, 150, 50)
            kilo = st.number_input("Kilo (kg)", 1, 50, 6)
            ilac = st.text_input("İlaç ve Doz (Sabah/Akşam)")
            alerji = st.text_input("Alerji Notu")
            submit = st.form_submit_button("🩺 Verileri Kaydet ve Gönder")
            
            if submit and isim:
                db.reference('/Basvurular').push({
                    'bebek_adi': isim, 'ates': ates, 'boy': boy, 'kilo': kilo,
                    'ilac': ilac if ilac else "Yok", 'alerji': alerji if alerji else "Yok",
                    'zaman': datetime.datetime.now().strftime("%d/%m %H:%M")
                })
                st.success("Bilgiler başarıyla iletildi!")

    with col2:
        st.subheader("💬 Doktorunuza Not Bırakın")
        mesaj = st.text_area("Örneğin: 'Bugün iştahı biraz azdı...'")
        if st.button("Mesajı İlet"):
            st.success("Mesajınız not alındı.")

# ==========================================
# 👨‍⚕️ DOKTOR PANELİ
# ==========================================
else:
    st.title("👨‍⚕️ ChildNest: Doktor Analiz Paneli")
    
    veriler = db.reference('/Basvurular').get()
    if veriler:
        df = pd.DataFrame(list(veriler.values()))
        
        # Bebek seçimi
        secilen = st.selectbox("İncelemek istediğiniz hasta:", df['bebek_adi'].unique())
        b_df = df[df['bebek_adi'] == secilen].sort_values(by='zaman')
        son = b_df.iloc[-1]
        
        # AI ÖZETİ
        analiz_metni, renk = ai_analiz(son['ates'])
        st.markdown(f"<div style='background:{renk}; padding:15px; border-radius:10px; color:white; text-align:center; font-weight:bold;'>{analiz_metni}</div>", unsafe_allow_html=True)
        
        # GRAFİKLER
        g1, g2 = st.columns(2)
        with g1:
            st.plotly_chart(px.line(b_df, x='zaman', y='ates', title="Ateş Trendi", markers=True), use_container_width=True)
        with g2:
            st.plotly_chart(px.line(b_df, x='zaman', y=['boy', 'kilo'], title="Büyüme Eğrisi", markers=True), use_container_width=True)
            
        # KLİNİK TABLO
        st.subheader("📋 Hasta Geçmişi")
        st.dataframe(b_df[['zaman', 'ates', 'boy', 'kilo', 'ilac', 'alerji']].iloc[::-1], use_container_width=True)
    else:
        st.warning("Henüz sisteme girilmiş bir veri yok.")
