import streamlit as st
import firebase_admin
from firebase_admin import credentials, db
import json
import pandas as pd
import plotly.express as px
import datetime

# Sayfa Yapılandırması
st.set_page_config(page_title="ChildNest: Anne & Doktor Paneli", page_icon="🩺", layout="wide")

# 1. FIREBASE BAĞLANTISI
if not firebase_admin._apps:
    key_dict = json.loads(st.secrets["textkey"])
    cred = credentials.Certificate(key_dict)
    firebase_admin.initialize_app(cred, {
        'databaseURL': "https://childnest-e3bab-default-rtdb.firebaseio.com/"
    })

# --- ÜST BAŞLIK ---
st.title("🛡️ ChildNest: Akıllı Bebek Takip ve Analiz Sistemi")
st.markdown("---")

# --- SOL PANEL: ANNELER İÇİN VERİ GİRİŞ ALANI ---
with st.sidebar:
    st.header("👩‍👦 Anne Giriş Bölümü")
    st.info("Bebeğinizin günlük ölçümlerini buradan kaydedebilirsiniz.")
    
    with st.form("anne_formu", clear_on_submit=True):
        bebek_adi = st.text_input("Bebeğin Adı")
        dogum_tarihi = st.date_input("Doğum Tarihi", datetime.date(2024, 1, 1))
        
        c1, c2 = st.columns(2)
        with c1:
            kilo = st.number_input("Kilo (kg)", 1.0, 50.0, 5.0)
        with c2:
            boy = st.number_input("Boy (cm)", 30.0, 150.0, 50.0)
            
        ates = st.number_input("Ateş (°C)", 35.0, 42.0, 37.0, 0.1)
        
        st.write("💊 **İlaç Takibi**")
        ilac = st.text_input("İlaç İsmi (Yoksa boş bırakın)")
        doz = st.selectbox("Dozaj Sıklığı", ["-", "Sabah", "Öğle", "Akşam", "Sabah-Akşam", "Sabah-Öğle-Akşam", "8 Saatte Bir"])
        alerji = st.text_input("⚠️ Alerji Notu")
        
        kaydet = st.form_submit_button("🩺 Verileri Doktora Gönder")
        
        if kaydet and bebek_adi:
            ref = db.reference('/Basvurular')
            ref.push({
                'bebek_adi': bebek_adi,
                'dogum_tarihi': str(dogum_tarihi),
                'kilo': kilo,
                'boy': boy,
                'ates': ates,
                'ilac': ilac if ilac else "Belirtilmedi",
                'doz': doz,
                'alerji': alerji if alerji else "Yok",
                'zaman': datetime.datetime.now().strftime("%d/%m %H:%M")
            })
            st.success("✅ Bilgiler başarıyla kaydedildi ve sisteme işlendi!")
            st.rerun()

# --- ANA PANEL: DOKTOR ANALİZ VE TAKİP ALANI ---
ref = db.reference('/Basvurular')
veriler = ref.get()

if veriler:
    df = pd.DataFrame(list(veriler.values()))
    
    # Doktor İçin Filtreleme
    st.subheader("👨‍⚕️ Doktor Analiz Paneli")
    secilen_bebek = st.selectbox("İncelemek İstediğiniz Hasta:", df['bebek_adi'].unique())
    bebek_df = df[df['bebek_adi'] == secilen_bebek].sort_values(by='zaman')

    # 📈 GRAFİKLER
    col_ates, col_gelisim = st.columns(2)
    
    with col_ates:
        st.markdown(f"**{secilen_bebek} - Ateş Seyri**")
        fig_ates = px.line(bebek_df, x='zaman', y='ates', markers=True, color_discrete_sequence=['#FF4B4B'])
        st.plotly_chart(fig_ates, use_container_width=True)
        
    with col_gelisim:
        st.markdown(f"**{secilen_bebek} - Boy & Kilo Gelişimi**")
        fig_gelisim = px.line(bebek_df, x='zaman', y=['boy', 'kilo'], markers=True)
        st.plotly_chart(fig_gelisim, use_container_width=True)

    # 📋 HASTA GEÇMİŞİ (KARTLAR)
    st.markdown("### 📜 Klinik Geçmiş")
    for i, row in bebek_df.iloc[::-1].iterrows():
        is_high_fever = row['ates'] >= 38.5
        with st.expander(f"📌 Tarih: {row['zaman']} | Durum: {'🚨 KRİTİK' if is_high_fever else '✅ STABİL'}"):
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("🌡️ Ateş", f"{row['ates']}°C")
            k2.metric("📏 Boy", f"{row['boy']} cm")
            k3.metric("⚖️ Kilo", f"{row['kilo']} kg")
            k4.write(f"💊 **İlaç:** {row['ilac']} ({row['doz']})")
            
            if row['alerji'] != "Yok":
                st.error(f"⚠️ **DİKKAT:** Bebeğin {row['alerji']} alerjisi bulunmaktadır!")

else:
    st.warning("🧐 Henüz sisteme girilmiş bir veri bulunmuyor. Sol taraftaki 'Anne Giriş Bölümü'nden kayıt yapabilirsiniz.")
