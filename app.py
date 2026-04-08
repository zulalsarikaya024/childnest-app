import streamlit as st
import firebase_admin
from firebase_admin import credentials, db
import json
import pandas as pd
import plotly.express as px
import datetime
from dateutil.relativedelta import relativedelta

# Sayfa Yapılandırması
st.set_page_config(page_title="ChildNest Pro", page_icon="💊", layout="wide")

# 1. FIREBASE BAĞLANTISI
if not firebase_admin._apps:
    key_dict = json.loads(st.secrets["textkey"])
    cred = credentials.Certificate(key_dict)
    firebase_admin.initialize_app(cred, {
        'databaseURL': "https://childnest-e3bab-default-rtdb.firebaseio.com/"
    })

# --- YARDIMCI FONKSİYONLAR ---
def yas_hesapla(dogum_tarihi_str):
    try:
        dogum = datetime.datetime.strptime(dogum_tarihi_str, "%Y-%m-%d").date()
        bugun = datetime.date.today()
        fark = relativedelta(bugun, dogum)
        return f"{fark.years} Yaş, {fark.months} Ay"
    except:
        return "Hesaplanamadı"

def ai_analiz(ates):
    ates = float(ates)
    if ates >= 39.5: return "🚨 KRİTİK: Çok yüksek ateş, acil müdahale gerekebilir!", "#ff4b4b"
    if ates >= 38.5: return "⚠️ UYARI: Yüksek ateş, doktora danışılmalı.", "#ffa500"
    return "✅ STABİL: Ateş normal sınırlar içinde.", "#2ecc71"

# --- ROL SEÇİMİ ---
st.sidebar.title("🚪 Giriş")
rol = st.sidebar.radio("Rolünüzü Seçin:", ["Ebeveyn Paneli 🏠", "Doktor Paneli 👨‍⚕️"])

# ==========================================
# 🏠 EBEVEYN PANELİ
# ==========================================
if rol == "Ebeveyn Paneli 🏠":
    st.title("🏠 Ebeveyn Takip Paneli")
    
    with st.expander("👶 Çocuk Kimlik Bilgileri"):
        c_isim = st.text_input("Çocuğun Adı", st.session_state.get('c_isim', ""))
        c_dogum = st.date_input("Doğum Tarihi", datetime.date(2024, 1, 1))
        if st.button("Kimliği Kaydet"):
            st.session_state['c_isim'] = c_isim
            st.session_state['c_dogum'] = str(c_dogum)
            st.success("Bilgiler Kaydedildi!")

    st.divider()

    if 'c_isim' in st.session_state and st.session_state['c_isim'] != "":
        current_age = yas_hesapla(st.session_state['c_dogum'])
        st.subheader(f"📝 {st.session_state['c_isim']} İçin Yeni Giriş")
        st.info(f"📊 Güncel Yaş: **{current_age}**")

        with st.form("yeni_giris", clear_on_submit=True):
            col1, col2, col3 = st.columns(3)
            with col1: ates = st.number_input("Ateş (°C)", 35.0, 42.0, 37.0, 0.1)
            with col2: boy = st.number_input("Boy (cm)", 30, 150, 50)
            with col3: kilo = st.number_input("Kilo (kg)", 1, 50, 6)
            
            st.markdown("---")
            st.write("💊 **İlaç Bilgileri**")
            col_ilac, col_doz = st.columns(2)
            with col_ilac:
                ilac_adi = st.text_input("İlaç Adı", placeholder="Örn: Calpol")
            with col_doz:
                dozaj = st.text_input("Dozaj Miktarı", placeholder="Örn: 5ml veya 1 Ölçek")
            
            doz_zaman = st.selectbox("Doz Zamanı", ["Belirtilmedi", "Sabah", "Öğle", "Akşam", "Sabah-Akşam", "8 Saatte Bir"])
            notlar = st.text_area("Eklemek İstediğiniz Notlar")
            
            if st.form_submit_button("🩺 Verileri Doktora Gönder"):
                db.reference('/Basvurular').push({
                    'bebek_adi': st.session_state['c_isim'],
                    'yas_ozet': current_age,
                    'ates': ates, 'boy': boy, 'kilo': kilo,
                    'ilac_adi': ilac_adi if ilac_adi else "Yok",
                    'dozaj': dozaj if dozaj else "Belirtilmedi",
                    'doz_zaman': doz_zaman,
                    'notlar': notlar if notlar else "Yok",
                    'zaman': datetime.datetime.now().strftime("%d/%m %H:%M")
                })
                st.success("Veriler başarıyla iletildi!")
    else:
        st.warning("Lütfen önce kimlik bilgilerini doldurun.")

# ==========================================
# 👨‍⚕️ DOKTOR PANELİ
# ==========================================
else:
    st.title("👨‍⚕️ Doktor Analiz Ekranı")
    veriler = db.reference('/Basvurular').get()
    
    if veriler:
        df = pd.DataFrame(list(veriler.values()))
        secilen = st.selectbox("Hasta Seçiniz:", df['bebek_adi'].unique())
        b_df = df[df['bebek_adi'] == secilen].sort_values(by='zaman')
        son = b_df.iloc[-1]
        
        # Özet Kartlar
        k1, k2, k3 = st.columns(3)
        k1.metric("Hasta", secilen)
        k2.metric("Yaş/Ay", son.get('yas_ozet', '-'))
        k3.metric("Son Ateş", f"{son['ates']}°C")

        # AI Durum Raporu
        rapor, renk = ai_analiz(son['ates'])
        st.markdown(f"<div style='background:{renk}; padding:15px; border-radius:10px; color:white; text-align:center; font-weight:bold;'>{rapor}</div>", unsafe_allow_html=True)
        
        # Grafikler
        g1, g2 = st.columns(2)
        with g1: st.plotly_chart(px.line(b_df, x='zaman', y='ates', title="Ateş Takibi", markers=True), use_container_width=True)
        with g2: st.plotly_chart(px.line(b_df, x='zaman', y=['boy', 'kilo'], title="Gelişim Takibi", markers=True), use_container_width=True)
            
        # Ayrıştırılmış Tablo
        st.subheader("📋 Detaylı Kayıt Listesi")
        display_df = b_df[['zaman', 'yas_ozet', 'ates', 'boy', 'kilo', 'ilac_adi', 'dozaj', 'doz_zaman', 'notlar']].iloc[::-1]
        st.table(display_df)
    else:
        st.info("Henüz veri girişi yapılmadı.")
