import streamlit as st
import firebase_admin
from firebase_admin import credentials, db
import json
import pandas as pd
import plotly.express as px
import datetime
from dateutil.relativedelta import relativedelta

# Sayfa Yapılandırması
st.set_page_config(page_title="ChildNest Pro: Sınırsız Takip", page_icon="📈", layout="wide")

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
        return f"{fark.years} Yaş, {fark.months} Ay, {fark.days} Gün"
    except:
        return "Hesaplanamadı"

def ai_analiz(ates):
    try:
        ates = float(ates)
        if ates >= 39.5: return "🚨 KRİTİK: Çok yüksek ateş!", "#ff4b4b"
        if ates >= 38.5: return "⚠️ UYARI: Yüksek ateş.", "#ffa500"
        return "✅ STABİL: Normal sınırlar.", "#2ecc71"
    except:
        return "Veri Analiz Edilemiyor", "#7f8c8d"

# --- ROL SEÇİMİ ---
st.sidebar.title("🚪 Giriş")
rol = st.sidebar.radio("Rolünüzü Seçin:", ["Ebeveyn Paneli 🏠", "Doktor Paneli 👨‍⚕️"])

# ==========================================
# 🏠 EBEVEYN PANELİ
# ==========================================
if rol == "Ebeveyn Paneli 🏠":
    st.title("🏠 Ebeveyn Takip Paneli (Sınırsız Giriş)")
    
    with st.expander("👶 Çocuk Kimlik Bilgileri"):
        c_isim = st.text_input("Çocuğun Adı", st.session_state.get('c_isim', ""))
        c_dogum = st.date_input("Doğum Tarihi", datetime.date(2024, 1, 1))
        if st.button("Kimliği Kaydet"):
            st.session_state['c_isim'] = c_isim
            st.session_state['c_dogum'] = str(c_dogum)
            st.success("Kimlik başarıyla oluşturuldu!")

    st.divider()

    if 'c_isim' in st.session_state and st.session_state['c_isim'] != "":
        current_age = yas_hesapla(st.session_state['c_dogum'])
        st.subheader(f"📝 {st.session_state['c_isim']} İçin Yeni Veri")
        st.info(f"📊 Bebeğin Tam Yaşı: **{current_age}**")

        with st.form("serbest_form", clear_on_submit=True):
            col1, col2, col3 = st.columns(3)
            with col1: ates = st.number_input("Ateş (°C)", step=0.1, format="%.1f")
            with col2: boy = st.number_input("Boy (cm)", step=0.1)
            with col3: kilo = st.number_input("Kilo (kg)", step=0.01)
            
            st.markdown("---")
            col_ilac, col_doz = st.columns(2)
            with col_ilac: ilac_adi = st.text_input("İlaç Adı")
            with col_doz: dozaj = st.text_input("Dozaj Miktarı")
            
            doz_zaman = st.text_input("Doz Zamanı (Serbest Metin)", placeholder="Örn: 6 saatte bir")
            notlar = st.text_area("Notlar / Semptomlar")
            
            if st.form_submit_button("🚀 Verileri Doktora İlet"):
                db.reference('/Basvurular').push({
                    'bebek_adi': st.session_state['c_isim'],
                    'yas_ozet': current_age,
                    'ates': ates, 'boy': boy, 'kilo': kilo,
                    'ilac_adi': ilac_adi if ilac_adi else "Yok",
                    'dozaj': dozaj if dozaj else "Yok",
                    'doz_zaman': doz_zaman if doz_zaman else "Belirtilmedi",
                    'notlar': notlar if notlar else "Yok",
                    'zaman': datetime.datetime.now().strftime("%d/%m/%y %H:%M")
                })
                st.success("Tüm veriler sınırsız formatta kaydedildi!")
    else:
        st.warning("Lütfen yukarıdan çocuk kimliğini oluşturun.")

# ==========================================
# 👨‍⚕️ DOKTOR PANELİ
# ==========================================
else:
    st.title("👨‍⚕️ Doktor Analiz Ekranı")
    veriler = db.reference('/Basvurular').get()
    
    if veriler:
        df = pd.DataFrame(list(veriler.values()))
        secilen = st.selectbox("İncelemek istediğiniz hasta:", df['bebek_adi'].unique())
        b_df = df[df['bebek_adi'] == secilen].sort_values(by='zaman')
        son = b_df.iloc[-1]
        
        st.metric("Güncel Yaş Bilgisi", son.get('yas_ozet', '-'))
        
        rapor, renk = ai_analiz(son['ates'])
        st.markdown(f"<div style='background:{renk}; padding:15px; border-radius:10px; color:white; text-align:center; font-weight:bold;'>{rapor}</div>", unsafe_allow_html=True)
        
        g1, g2 = st.columns(2)
        with g1: st.plotly_chart(px.line(b_df, x='zaman', y='ates', title="Serbest Ölçek Ateş Grafiği", markers=True), use_container_width=True)
        with g2: st.plotly_chart(px.line(b_df, x='zaman', y=['boy', 'kilo'], title="Serbest Ölçek Gelişim Analizi", markers=True), use_container_width=True)
            
        st.subheader("📋 Klinik Veri Özeti")
        st.dataframe(b_df[['zaman', 'yas_ozet', 'ates', 'boy', 'kilo', 'ilac_adi', 'dozaj', 'doz_zaman', 'notlar']].iloc[::-1], use_container_width=True)
    else:
        st.info("Henüz veri girilmemiş.")
