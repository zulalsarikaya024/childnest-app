import streamlit as st
import firebase_admin
from firebase_admin import credentials, db
import json

# Sayfa Ayarları
st.set_page_config(page_title="ChildNest Doktor Paneli", page_icon="🏥")

# 1. FIREBASE BAĞLANTISI (SİHİRLİ KISIM)
if not firebase_admin._apps:
    # GitHub'a yükleyeceğimiz sırlar (Secrets) kısmından anahtarı alacağız
    key_dict = json.loads(st.secrets["textkey"])
    cred = credentials.Certificate(key_dict)
    firebase_admin.initialize_app(cred, {
        'databaseURL': "https://childnest-e3bab-default-rtdb.firebaseio.com/"
    })

st.title("🏥 ChildNest Doktor Paneli")
st.subheader("Canlı Hasta Takip Ekranı")

# 2. VERİLERİ ÇEK VE GÖSTER
try:
    ref = db.reference('/Basvurular')
    tum_veriler = ref.get()

    if tum_veriler:
        for key, veri in tum_veriler.items():
            ates = float(veri.get('ates', 0))
            
            # Ateşe göre renkli kutucuklar
            if ates >= 38.5:
                st.error(f"🚨 **{veri.get('bebek_adi')}** - Ateş: {ates}°C (ACİL)")
            else:
                st.success(f"✅ **{veri.get('bebek_adi')}** - Ateş: {ates}°C (Normal)")
            
            with st.expander("Detayları Gör"):
                st.write(f"Durum: {veri.get('durum')}")
                st.write(f"Zaman: {veri.get('zaman')}")
    else:
        st.info("Henüz bekleyen başvuru yok.")

except Exception as e:
    st.error(f"Bir hata oluştu: {e}")
