import streamlit as st
import firebase_admin
from firebase_admin import credentials, db
import json
import pandas as pd
import plotly.express as px
import datetime
from dateutil.relativedelta import relativedelta

# Sayfa Yapılandırması
st.set_page_config(page_title="ChildNest Pro", page_icon="🏥", layout="wide")

# 1. FIREBASE BAĞLANTISI
if not firebase_admin._apps:
    key_dict = json.loads(st.secrets["textkey"])
    cred = credentials.Certificate(key_dict)
    firebase_admin.initialize_app(cred, {
        'databaseURL': "https://childnest-e3bab-default-rtdb.firebaseio.com/"
    })

# --- YARDIMCI FONKSİYONLAR ---
def yas_hesapla(dogum_tarihi_str):
    """Doğum tarihinden bugüne tam yaş ve ay hesaplar."""
    try:
        dogum = datetime.datetime.strptime(dogum_tarihi_str, "%Y-%m-%d").date()
        bugun = datetime.date.today()
        fark = relativedelta(bugun, dogum)
        return f"{fark.years} Yaş, {fark.months} Ay"
    except:
        return "Hesaplanamadı"

def ai_analiz(ates):
    """Ateş durumuna göre AI ön analizi yapar."""
    ates = float(ates)
    if ates >= 39.5: return "🚨 KRİTİK: Çok yüksek ateş, acil müdahale gerekebilir!", "#ff4b4b"
    if ates >= 38.5: return "⚠️ UYARI: Yüksek ateş, doktora danışılmalı.", "#ffa500"
    return "✅ STABİL: Ateş normal sınırlar içinde.", "#2ecc71"

# --- ROL SEÇİMİ (Giriş Kapısı) ---
st.sidebar.title("🚪 ChildNest Giriş")
rol = st.sidebar.radio("Rolünüzü Seçin:", ["Ebeveyn Paneli 🏠", "Doktor Paneli 👨‍⚕️"])

# ==========================================
# 🏠 EBEVEYN PANELİ
# ==========================================
if rol == "Ebeveyn Paneli 🏠":
    st.title("🏠 Ebeveyn Yönetim ve Takip Ekranı")
    st.markdown("Bebeğinizin gelişimini kaydedin ve doktorunuzla paylaşın.")

    # ÇOCUK BİLGİLERİNİ KAYDETME (Tarayıcı belleğinde tutulur)
    with st.expander("👶 Çocuk Kimlik Bilgileri (Bir kez ayarlamanız yeterli)"):
        c_isim = st.text_input("Çocuğun Adı", st.session_state.get('c_isim', ""))
        c_dogum = st.date_input("Doğum Tarihi", datetime.date(2024, 1, 1))
        if st.button("Kimliği Kaydet"):
            st.session_state['c_isim'] = c_isim
            st.session_state['c_dogum'] = str(c_dogum)
            st.success(f"{c_isim} bilgileri kaydedildi!")

    st.divider()

    # ÖLÇÜM GİRİŞ FORMU
    if 'c_isim' in st.session_state and st.session_state['c_isim'] != "":
        current_age = yas_hesapla(st.session_state['c_dogum'])
        st.subheader(f"📝 {st.session_state['c_isim']} için Yeni Ölçüm")
        st.info(f"📊 Bebeğiniz şu an: **{current_age}**")

        with st.form("olcum_formu", clear_on_submit=True):
            col1, col2, col3 = st.columns(3)
            with col1: ates = st.number_input("Vücut Isısı (°C)", 35.0, 42.0, 37.0, 0.1)
            with col2: boy = st.number_input("Boy (cm)", 30, 150, 50)
            with col3: kilo = st.number_input("Kilo (kg)", 1, 50, 6)
            
            ilac = st.text_input("Kullanılan İlaç ve Dozaj (Örn: Calpol 5ml)")
            notlar = st.text_area("Doktora iletmek istediğiniz özel bir not var mı?")
            
            if st.form_submit_button("🚀 Verileri Sisteme Gönder"):
                ref = db.reference('/Basvurular')
                ref.push({
                    'bebek_adi': st.session_state['c_isim'],
                    'yas_ozet': current_age,
                    'ates': ates, 'boy': boy, 'kilo': kilo,
                    'ilac': ilac if ilac else "Yok",
                    'notlar': notlar if notlar else "Yok",
                    'zaman': datetime.datetime.now().strftime("%d/%m %H:%M")
                })
                st.success("Veriler başarıyla doktorun paneline iletildi!")
    else:
        st.warning("Lütfen önce 'Çocuk Kimlik Bilgileri' kısmından çocuğun adını ve doğum tarihini girin.")

# ==========================================
# 👨‍⚕️ DOKTOR PANELİ
# ==========================================
else:
    st.title("👨‍⚕️ Doktor Analiz ve Karar Destek Paneli")
    
    veriler = db.reference('/Basvurular').get()
    
    if veriler:
        df = pd.DataFrame(list(veriler.values()))
        
        # Hasta seçimi ve Filtreleme
        secilen_hasta = st.selectbox("İncelemek istediğiniz hasta:", df['bebek_adi'].unique())
        b_df = df[df['bebek_adi'] == secilen_hasta].sort_values(by='zaman')
        son_kayit = b_df.iloc[-1]
        
        # ÜST ÖZET METRİKLERİ
        m1, m2, m3 = st.columns(3)
        m1.metric("👶 Hasta", secilen_hasta)
        m2.metric("📅 Güncel Yaş/Ay", son_kayit.get('yas_ozet', 'Belirtilmedi'))
        m3.metric("🌡️ Son Ateş", f"{son_kayit['ates']}°C")

        # AI ANALİZ RAPORU
        analiz_notu, renk = ai_analiz(son_kayit['ates'])
        st.markdown(f"""
        <div style="background-color: {renk}; padding: 15px; border-radius: 10px; color: white; text-align: center; font-weight: bold; font-size: 1.2em;">
            {analiz_notu}
        </div>
        """, unsafe_allow_html=True)
        
        st.divider()

        # GRAFİKLER
        g1, g2 = st.columns(2)
        with g1:
            st.plotly_chart(px.line(b_df, x='zaman', y='ates', title="Ateş Trend Analizi", markers=True), use_container_width=True)
        with g2:
            st.plotly_chart(px.line(b_df, x='zaman', y=['boy', 'kilo'], title="Fiziksel Gelişim Eğrisi", markers=True), use_container_width=True)
            
        # KLİNİK GEÇMİŞ TABLOSU
        st.subheader("📋 Tüm Klinik Kayıtlar")
        st.table(b_df[['zaman', 'yas_ozet', 'ates', 'boy', 'kilo', 'ilac', 'notlar']].iloc[::-1])
    else:
        st.info("Henüz veritabanında kayıtlı bir hasta verisi bulunamadı.")
