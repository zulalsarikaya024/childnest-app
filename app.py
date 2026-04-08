import streamlit as st
import firebase_admin
from firebase_admin import credentials, db
import json
import pandas as pd
import plotly.express as px # Daha gelişmiş grafikler için

# Sayfa Genişliği
st.set_page_config(page_title="ChildNest Pro: Gelişim Analizi", page_icon="📊", layout="wide")

if not firebase_admin._apps:
    key_dict = json.loads(st.secrets["textkey"])
    cred = credentials.Certificate(key_dict)
    firebase_admin.initialize_app(cred, {
        'databaseURL': "https://childnest-e3bab-default-rtdb.firebaseio.com/"
    })

st.title("🏥 ChildNest: Kişiselleştirilmiş Gelişim ve Sağlık Paneli")

# --- VERİ ÇEKME ---
ref = db.reference('/Basvurular')
veriler = ref.get()

if veriler:
    df = pd.DataFrame(list(veriler.values()))
    
    # --- ÜST PANEL: FİLTRELEME (ÖZEL AYAR) ---
    st.subheader("🔍 Filtrele ve İncele")
    secilen_bebek = st.selectbox("Hangi bebeğin verilerini incelemek istersiniz?", df['bebek_adi'].unique())
    
    # Sadece seçilen bebeğin verilerini al
    bebek_df = df[df['bebek_adi'] == secilen_bebek].sort_values(by='zaman')

    # --- GRAFİKLER BÖLÜMÜ ---
    col_grafik1, col_grafik2 = st.columns(2)

    with col_grafik1:
        st.markdown(f"### 🌡️ {secilen_bebek} - Ateş Seyri")
        # Plotly ile daha interaktif grafik
        fig_ates = px.line(bebek_df, x='zaman', y='ates', markers=True, 
                          color_discrete_sequence=['#ff4b4b'], title="Ateş Değişimi (°C)")
        st.plotly_chart(fig_ates, use_container_width=True)

    with col_grafik2:
        st.markdown(f"### ⚖️ {secilen_bebek} - Boy & Kilo Gelişimi")
        # Boy ve Kilo verilerini aynı grafikte gösterelim
        fig_gelisim = px.line(bebek_df, x='zaman', y=['boy', 'kilo'], markers=True,
                             title="Gelişim Takibi (Boy/Kilo)")
        st.plotly_chart(fig_gelisim, use_container_width=True)

    st.divider()

    # --- DETAYLI KARTLAR ---
    st.subheader(f"📋 {secilen_bebek} İçin Tüm Kayıtlar")
    for i, row in bebek_df.iloc[::-1].iterrows(): # En yeni kaydı en üstte göster
        is_critical = row['ates'] >= 38.5
        with st.expander(f"📌 {row['zaman']} Tarihli Kayıt - {'🚨 KRİTİK' if is_critical else '✅ Normal'}"):
            c1, c2, c3 = st.columns(3)
            c1.metric("Boy", f"{row['boy']} cm")
            c2.metric("Kilo", f"{row['kilo']} kg")
            c3.metric("Ateş", f"{row['ates']} °C", delta=f"{row['ates']-37:.1f}", delta_color="inverse")
            
            st.info(f"💊 **İlaç
