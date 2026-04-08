import streamlit as st
import firebase_admin
from firebase_admin import credentials, db
import json
import pandas as pd
import datetime

# Sayfa Genişliği ve Başlık
st.set_page_config(page_title="ChildNest Pro", page_icon="👶", layout="wide")

# 1. FIREBASE BAĞLANTISI
if not firebase_admin._apps:
    key_dict = json.loads(st.secrets["textkey"])
    cred = credentials.Certificate(key_dict)
    firebase_admin.initialize_app(cred, {
        'databaseURL': "https://childnest-e3bab-default-rtdb.firebaseio.com/"
    })

st.title("🏥 ChildNest: Profesyonel Bebek Sağlık Sistemi")

# --- SOL PANEL: GELİŞMİŞ KAYIT FORMU ---
with st.sidebar:
    st.header("📝 Yeni Hasta Kaydı")
    with st.form("saglik_formu"):
        isim = st.text_input("Bebek Adı")
        dogum_gunu = st.date_input("Doğum Tarihi", datetime.date(2024, 1, 1))
        
        c1, c2 = st.columns(2)
        with c1:
            kilo = st.number_input("Kilo (kg)", 1.0, 50.0, 5.0)
        with c2:
            boy = st.number_input("Boy (cm)", 30.0, 150.0, 50.0)
            
        ates = st.number_input("Ateş (°C)", 35.0, 42.0, 37.0, 0.1)
        
        st.subheader("💊 İlaç ve Alerji Bilgisi")
        ilac = st.text_input("İlaç Adı")
        doz = st.selectbox("Dozaj Zamanı", ["Belirtilmedi", "Sabah", "Öğle", "Akşam", "Sabah-Akşam", "Sabah-Öğle-Akşam"])
        alerji = st.text_input("⚠️ Bilinen Alerjiler")
        
        submit = st.form_submit_button("Kaydı Tamamla")
        
        if submit and isim:
            ref = db.reference('/Basvurular')
            ref.push({
                'bebek_adi': isim,
                'dogum_tarihi': str(dogum_gunu),
                'kilo': kilo,
                'boy': boy,
                'ates': ates,
                'ilac': ilac if ilac else "Yok",
                'doz': doz,
                'alerji': alerji if alerji else "Yok",
                'zaman': datetime.datetime.now().strftime("%d/%m %H:%M")
            })
            st.success(f"{isim} başarıyla kaydedildi!")

# --- ANA EKRAN: ANALİZ VE TAKİP ---
ref = db.reference('/Basvurular')
veriler = ref.get()

if veriler:
    df = pd.DataFrame(list(veriler.values()))

    # Üst Bölüm: Ateş Grafiği
    st.subheader("📈 Genel Ateş Seyri")
    st.line_chart(df.set_index('zaman')['ates'])

    # Alt Bölüm: Detaylı Hasta Kartları
    st.subheader("📋 Aktif Takip Listesi")
    cols = st.columns(2)
    
    for i, row in df.iterrows():
        with cols[i % 2]:
            # Kritik Durum Kontrolü (Ateş > 38.5 veya Alerji varsa kırmızı)
            is_critical = row['ates'] >= 38.5 or row['alerji'] != "Yok"
            border_color = "#ff4b4b" if is_critical else "#2ecc71"
            bg_color = "#fff5f5" if is_critical else "#f9fcf9"
            
            st.markdown(f"""
            <div style="border: 2px solid {border_color}; border-radius: 15px; padding: 20px; background-color: {bg_color}; margin-bottom: 20px; font-family: sans-serif;">
                <h2 style="margin:0; color:#2c3e50;">👶 {row['bebek_adi']}</h2>
                <p style="color:gray; font-size: 0.9em;">📅 Doğum Tarihi: {row['dogum_tarihi']}</p>
                <hr style="border: 0.5px solid {border_color};">
                <div style="display: flex; justify-content: space-between; font-size: 1.1em;">
                    <span>⚖️ <b>{row['kilo']} kg</b></span>
                    <span>📏 <b>{row['boy']} cm</b></span>
                    <span>🌡️ <b style="color:{border_color};">{row['ates']}°C</b></span>
                </div>
                <div style="margin-top: 15px; background: white; padding: 10px; border-radius: 10px; border: 1px inset #eee;">
                    <p style="margin:2px;">💊 <b>İlaç:</b> {row['ilac']} ({row['doz']})</p>
                    <p style="margin:2px; color:{'#d35400' if row['alerji'] != 'Yok' else '#27ae60'};">
                        ⚠️ <b>Alerji:</b> {row['alerji']}
                    </p>
                </div>
                <p style="font-size: 0.7em; text-align: right; margin-top: 10px; color: #7f8c8d;">⏱ Kayıt: {row['zaman']}</p>
            </div>
            """, unsafe_allow_html=True)
else:
    st.info("Henüz veri girişi yapılmadı. Lütfen sol taraftaki formu doldurun.")
