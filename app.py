import streamlit as st
import firebase_admin
from firebase_admin import credentials, db
import json
import pandas as pd
import plotly.express as px
import datetime
from dateutil.relativedelta import relativedelta

# Sayfa Yapılandırması
st.set_page_config(page_title="ChildNest Pro: Tedavi Yönetimi", page_icon="💊", layout="wide")

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

# --- ROL SEÇİMİ ---
st.sidebar.title("🚪 Giriş")
rol = st.sidebar.radio("Rolünüzü Seçin:", ["Ebeveyn Paneli 🏠", "Doktor Paneli 👨‍⚕️"])

# ==========================================
# 👨‍⚕️ DOKTOR PANELİ (Önce Doktor Ayarlar)
# ==========================================
if rol == "Doktor Paneli 👨‍⚕️":
    st.title("👨‍⚕️ Doktor Tedavi ve Analiz Paneli")
    veriler = db.reference('/Basvurular').get()
    
    if veriler:
        df = pd.DataFrame(list(veriler.values()))
        secilen = st.selectbox("İncelemek istediğiniz hasta:", df['bebek_adi'].unique())
        
        # 💊 İLAÇ ATAMA BÖLÜMÜ (Yeni Özellik)
        st.subheader(f"💊 {secilen} İçin İlaç/Dozaj Ata")
        with st.form("ilac_atama"):
            atanan_ilac = st.text_input("Reçete Edilecek İlaç")
            atanan_doz = st.text_input("Önerilen Dozaj (Örn: 5ml, 1/2 Tablet)")
            talimat = st.text_area("Kullanım Talimatı")
            if st.form_submit_button("Reçeteyi Ebeveyne Gönder"):
                db.reference(f'/Receteler/{secilen}').set({
                    'ilac': atanan_ilac,
                    'doz': atanan_doz,
                    'talimat': talimat,
                    'tarih': datetime.datetime.now().strftime("%d/%m/%y %H:%M")
                })
                st.success("Reçete ebeveyn paneline başarıyla iletildi!")

        st.divider()
        # ANALİZ VE GRAFİKLER
        b_df = df[df['bebek_adi'] == secilen].sort_values(by='zaman')
        st.metric("Güncel Yaş", yas_hesapla(st.session_state.get('c_dogum', "2024-01-01")))
        st.plotly_chart(px.line(b_df, x='zaman', y='ates', title="Ateş Grafiği"), use_container_width=True)
        st.table(b_df[['zaman', 'ates', 'boy', 'kilo', 'notlar']].iloc[::-1])
    else:
        st.info("Kayıtlı hasta bulunamadı.")

# ==========================================
# 🏠 EBEVEYN PANELİ
# ==========================================
else:
    st.title("🏠 Ebeveyn Takip Paneli")
    
    # Kimlik Bilgileri
    with st.expander("👶 Çocuk Kimlik Bilgileri"):
        c_isim = st.text_input("Çocuğun Adı", st.session_state.get('c_isim', ""))
        c_dogum = st.date_input("Doğum Tarihi", datetime.date(2024, 1, 1))
        if st.button("Kaydet"):
            st.session_state['c_isim'] = c_isim
            st.session_state['c_dogum'] = str(c_dogum)
            st.rerun()

    if 'c_isim' in st.session_state and st.session_state['c_isim'] != "":
        st.info(f"📊 Bebeğiniz: **{st.session_state['c_isim']}** | Yaş: **{yas_hesapla(st.session_state['c_dogum'])}**")
        
        # 💊 DOKTORDAN GELEN REÇETE (Doktorun atadığı burada görünür)
        recete_ref = db.reference(f'/Receteler/{st.session_state["c_isim"]}').get()
        if recete_ref:
            st.warning(f"🩺 **DOKTORUNUZUN TALİMATI:** \n\n **İlaç:** {recete_ref['ilac']} \n\n **Dozaj:** {recete_ref['doz']} \n\n **Not:** {recete_ref['talimat']}")
        
        st.divider()
        
        # Ölçüm Girişi
        with st.form("olcum_ve_doz_istegi"):
            st.subheader("📝 Günlük Ölçüm ve Dozaj Bildirimi")
            ates = st.number_input("Ateş (°C)", step=0.1)
            boy = st.number_input("Boy (cm)", step=0.1)
            kilo = st.number_input("Kilo (kg)", step=0.01)
            
            doz_onayi = st.checkbox("✅ Doktorun verdiği ilacı uyguladım.")
            ebeveyn_notu = st.text_area("Dozaj sonrası gözleminiz veya sorunuz")
            
            if st.form_submit_button("Verileri Gönder"):
                db.reference('/Basvurular').push({
                    'bebek_adi': st.session_state['c_isim'],
                    'ates': ates, 'boy': boy, 'kilo': kilo,
                    'doz_durumu': "Uygulandı" if doz_onayi else "Uygulanmadı",
                    'notlar': ebeveyn_notu,
                    'zaman': datetime.datetime.now().strftime("%d/%m/%y %H:%M")
                })
                st.success("Bilgiler iletildi.")
