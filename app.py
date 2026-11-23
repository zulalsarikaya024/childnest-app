"""
ChildNest — Pilot Kullanılabilirlik Çalışması Sürümü

Bu uygulama bilimsel bir araştırma (kullanılabilirlik ve ebeveyn-hekim iletişimi
pilot çalışması) için hazırlanmıştır. Tanı veya tedavi önerisi sunmaz.

Veri modeli (kimliksiz / takma adlı):
  /katilimcilar/{kod}   -> {yas_ay, kilo, guncelleme}
  /kayitlar/{push_id}   -> semptom ve ilaç kayıtları
  /telemetri/{push_id}  -> anonim kullanım olayları (süre, kırmızı bayrak vb.)
"""

import datetime as dt
import hmac
import html
import json
import re
import uuid
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(page_title="ChildNest — Pilot Çalışma", page_icon="🧪", layout="wide")

# ---------------------------------------------------------------------------
# SABİTLER
# ---------------------------------------------------------------------------
TZ = ZoneInfo("Europe/Istanbul")
KOD_DESENI = re.compile(r"^[A-Z]\d{2,3}$")  # A01, B12, D105 ...
ATES_ESIGI = 39.0                            # bu değer ve üzeri -> kırmızı bayrak
BEBEK_ATES_ESIGI = 38.0                      # 3 aydan küçükte bu değer ve üzeri -> kırmızı bayrak
FORM_HEDEF_SN = 120                          # "2 dakikada doldurulabilir" hedefi

KRITIK_SEMPTOMLAR = [
    "Nefes darlığı / hızlı nefes",
    "Bilinç değişikliği / uyandırmakta güçlük",
    "Havale (nöbet)",
    "Dudak/cilt morarması",
    "Bastırınca solmayan döküntü",
    "Ense sertliği",
    "Sıvı alamama / 8 saattir idrar yok",
]
DIGER_SEMPTOMLAR = [
    "Öksürük", "Burun akıntısı", "Boğaz ağrısı", "Kulak ağrısı", "Kusma",
    "İshal", "İştahsızlık", "Huzursuzluk", "Döküntü (solan)", "Halsizlik",
]
DOZ_BIRIMLERI = ["ml", "mg", "damla", "tablet", "ölçek"]

UYARI_METNI = (
    "Bu platform **bilimsel araştırma ve kullanılabilirlik testi** amacıyla hazırlanmıştır. "
    "**Tanı veya tedavi önerisi sunmaz;** acil durumlarda en yakın sağlık kuruluşuna "
    "başvurunuz (☎️ **112**)."
)


def simdi() -> dt.datetime:
    return dt.datetime.now(TZ)


# ---------------------------------------------------------------------------
# VERİ DEPOSU: Firebase varsa onu, yoksa yerel JSON dosyasını kullanır
# ---------------------------------------------------------------------------
def _secret(anahtar, varsayilan=None):
    try:
        return st.secrets[anahtar]
    except Exception:
        return varsayilan


class FirebaseDepo:
    ad = "Firebase"

    def __init__(self, key_json: str, url: str):
        import firebase_admin
        from firebase_admin import credentials, db

        if not firebase_admin._apps:
            firebase_admin.initialize_app(
                credentials.Certificate(json.loads(key_json)), {"databaseURL": url}
            )
        self._db = db

    def ekle(self, yol, veri):
        self._db.reference(yol).push(veri)

    def yaz(self, yol, veri):
        self._db.reference(yol).set(veri)

    def oku(self, yol):
        return self._db.reference(yol).get() or {}


class YerelDepo:
    """Firebase anahtarı yoksa (yerel deneme / demo) veriyi data/ klasörüne yazar."""

    ad = "Yerel dosya (demo)"

    def __init__(self, dosya="data/childnest_yerel.json"):
        self.dosya = Path(dosya)
        self.dosya.parent.mkdir(exist_ok=True)

    def _yukle(self):
        return json.loads(self.dosya.read_text("utf-8")) if self.dosya.exists() else {}

    def _kaydet(self, veri):
        self.dosya.write_text(json.dumps(veri, ensure_ascii=False, indent=1), "utf-8")

    def _dugum(self, kok, yol, olustur=False):
        dugum = kok
        for parca in [p for p in yol.split("/") if p]:
            if parca not in dugum:
                if not olustur:
                    return None
                dugum[parca] = {}
            dugum = dugum[parca]
        return dugum

    def ekle(self, yol, veri):
        kok = self._yukle()
        self._dugum(kok, yol, olustur=True)[uuid.uuid4().hex] = veri
        self._kaydet(kok)

    def yaz(self, yol, veri):
        kok = self._yukle()
        *ust, son = [p for p in yol.split("/") if p]
        self._dugum(kok, "/".join(ust), olustur=True)[son] = veri
        self._kaydet(kok)

    def oku(self, yol):
        return self._dugum(self._yukle(), yol) or {}


@st.cache_resource
def depo_al():
    key = _secret("textkey")
    if key:
        url = _secret("database_url", "https://childnest-e3bab-default-rtdb.firebaseio.com/")
        return FirebaseDepo(key, url)
    return YerelDepo()


depo = depo_al()


# ---------------------------------------------------------------------------
# TELEMETRİ (anonim: yalnızca katılımcı kodu + oturum kimliği + olay)
# ---------------------------------------------------------------------------
if "oturum_id" not in st.session_state:
    st.session_state.oturum_id = uuid.uuid4().hex[:12]


def telemetri(olay: str, rol: str, katilimci: str | None = None, **ek):
    depo.ekle("/telemetri", {
        "oturum_id": st.session_state.oturum_id,
        "rol": rol,
        "katilimci": katilimci or "",
        "olay": olay,
        "zaman": simdi().isoformat(timespec="seconds"),
        **ek,
    })


# ---------------------------------------------------------------------------
# YARDIMCILAR
# ---------------------------------------------------------------------------
def yas_metni(yas_ay) -> str:
    if yas_ay is None:
        return "—"
    yas_ay = int(yas_ay)
    if yas_ay < 24:
        return f"{yas_ay} ay"
    yil, ay = divmod(yas_ay, 12)
    return f"{yil} yaş {ay} ay" if ay else f"{yil} yaş"


def kirmizi_bayrak_nedenleri(ates, semptomlar, yas_ay) -> list[str]:
    nedenler = []
    if ates is not None and ates >= ATES_ESIGI:
        nedenler.append(f"Ateş {ates:.1f} °C (≥ {ATES_ESIGI:.1f})")
    if ates is not None and yas_ay is not None and yas_ay < 3 and ates >= BEBEK_ATES_ESIGI:
        nedenler.append(f"3 aydan küçük bebekte ateş {ates:.1f} °C (≥ {BEBEK_ATES_ESIGI:.1f})")
    nedenler += [s for s in (semptomlar or []) if s in KRITIK_SEMPTOMLAR]
    return nedenler


def kirmizi_bayrak_kutusu(nedenler):
    st.error(
        "## 🚨 Acil Tıbbi Değerlendirme Gerekebilir\n"
        + "\n".join(f"- {n}" for n in nedenler)
        + "\n\n**Lütfen beklemeden en yakın sağlık kuruluşuna başvurun veya 112'yi arayın.** "
        "Bu platform hekiminize anlık bildirim göndermez."
    )


def kayitlari_getir(katilimci=None) -> pd.DataFrame:
    veri = depo.oku("/kayitlar")
    df = pd.DataFrame(list(veri.values())) if veri else pd.DataFrame()
    if df.empty:
        return df
    if katilimci:
        df = df[df["katilimci"] == katilimci]
    df["zaman_dt"] = pd.to_datetime(df["zaman"])
    return df.sort_values("zaman_dt").reset_index(drop=True)


# ---------------------------------------------------------------------------
# GİRİŞ EKRANI ORTAK ÖĞELER
# ---------------------------------------------------------------------------
st.warning(UYARI_METNI, icon="⚠️")

st.sidebar.title("🧪 ChildNest Pilot")
rol = st.sidebar.radio("Rolünüzü seçin:", ["Ebeveyn", "Hekim", "Araştırmacı"])
st.sidebar.caption(f"Veri deposu: {depo.ad}")


def sifre_kontrol(secret_adi: str, etiket: str) -> bool:
    """Hekim/araştırmacı panelleri için basit erişim şifresi (st.secrets içinde)."""
    beklenen = _secret(secret_adi)
    if not beklenen:
        st.error(f"Bu panel kapalı: `{secret_adi}` secrets içinde tanımlı değil.")
        return False
    durum = f"giris_{secret_adi}"
    if st.session_state.get(durum):
        return True
    girilen = st.text_input(f"{etiket} erişim şifresi", type="password")
    if girilen:
        if hmac.compare_digest(girilen.encode(), str(beklenen).encode()):
            st.session_state[durum] = True
            st.rerun()
        st.error("Şifre hatalı.")
    return False


# ===========================================================================
# 🏠 EBEVEYN PANELİ
# ===========================================================================
def ebeveyn_paneli():
    st.title("🏠 Semptom ve İlaç Kayıt Formu")

    # --- 1) Katılımcı girişi (kimlik bilgisi yok, yalnızca kod) ---
    if not st.session_state.get("katilimci"):
        with st.form("katilimci_giris"):
            kod = st.text_input("Katılımcı Kodu", placeholder="Örn: A01",
                                help="Araştırma ekibinin size verdiği kod.").strip().upper()
            onam = st.checkbox("Bilgilendirilmiş onam formunu okudum ve imzaladım.")
            if st.form_submit_button("Giriş", type="primary"):
                if not KOD_DESENI.match(kod):
                    st.error("Kod biçimi geçersiz. Örnek: A01")
                elif not onam:
                    st.error("Devam etmek için onam kutusunu işaretleyin.")
                else:
                    st.session_state.katilimci = kod
                    telemetri("oturum_acildi", "ebeveyn", kod)
                    st.rerun()
        return

    kod = st.session_state.katilimci
    profil = depo.oku(f"/katilimcilar/{kod}")

    c1, c2 = st.columns([4, 1])
    c1.info(f"Katılımcı: **{kod}** · Çocuğun yaşı: **{yas_metni(profil.get('yas_ay'))}** · "
            f"Kilo: **{profil.get('kilo', '—')} kg**")
    if c2.button("Çıkış"):
        for k in list(st.session_state.keys()):
            if k != "oturum_id":
                del st.session_state[k]
        st.rerun()

    # --- 2) Çocuk bilgisi: yalnızca yaş (ay/yıl) ve kilo ---
    with st.expander("👶 Çocuk Bilgisi (yaş ve kilo)", expanded=not profil):
        with st.form("profil"):
            a, b, c = st.columns(3)
            yas_deger = a.number_input("Çocuğun yaşı", min_value=0, max_value=216, step=1,
                                       value=int(profil.get("yas_ay", 12)))
            yas_birim = b.radio("Birim", ["Ay", "Yıl"], horizontal=True)
            kilo = c.number_input("Kilo (kg)", min_value=1.0, max_value=120.0, step=0.1,
                                  value=float(profil.get("kilo", 10.0)))
            if st.form_submit_button("Kaydet"):
                yas_ay = yas_deger if yas_birim == "Ay" else yas_deger * 12
                if yas_ay > 216:
                    st.error("Yaş 18 yıldan büyük olamaz.")
                else:
                    depo.yaz(f"/katilimcilar/{kod}", {
                        "yas_ay": int(yas_ay), "kilo": round(kilo, 1),
                        "guncelleme": simdi().isoformat(timespec="seconds"),
                    })
                    st.rerun()
    if not profil:
        st.stop()

    kayit_formu(kod, profil)


def _ilk_etkilesim():
    """Herhangi bir form alanına ilk dokunulduğu an (tamamlama süresinin başlangıcı)."""
    if st.session_state.get("form_ilk_etkilesim") is None:
        st.session_state.form_ilk_etkilesim = simdi()


def kayit_formu(kod, profil):
    ss = st.session_state
    ss.setdefault("form_no", 0)                 # her kayıttan sonra formu sıfırlamak için
    ss.setdefault("form_acilis", simdi())        # form ekrana geldiği an
    ss.setdefault("form_ilk_etkilesim", None)
    ss.setdefault("form_bayrak_sayisi", 0)       # bu form doldurulurken kaç kez tetiklendi
    ss.setdefault("onceki_bayrak", False)
    n = ss.form_no

    st.subheader("📝 Yeni Kayıt")
    st.caption("Yaklaşık 1–2 dakika sürer. Yalnızca bildiğiniz alanları doldurun.")

    with st.container(border=True):
        st.markdown("**1. Ateş**")
        ates = st.number_input("Ateş (°C) — ölçmediyseniz boş bırakın", min_value=34.0,
                               max_value=43.0, step=0.1, value=None, format="%.1f",
                               key=f"ates_{n}", on_change=_ilk_etkilesim)

        st.markdown("**2. Belirtiler**")
        kritik = st.pills("⚠️ Acil belirtiler", KRITIK_SEMPTOMLAR, selection_mode="multi",
                          key=f"kritik_{n}", on_change=_ilk_etkilesim)
        diger = st.pills("Diğer belirtiler", DIGER_SEMPTOMLAR, selection_mode="multi",
                         key=f"diger_{n}", on_change=_ilk_etkilesim)
        semptomlar = list(kritik or []) + list(diger or [])

        # Kırmızı bayrak: kayıt beklenmeden, alan değiştiği anda gösterilir
        nedenler = kirmizi_bayrak_nedenleri(ates, semptomlar, profil.get("yas_ay"))
        if nedenler:
            kirmizi_bayrak_kutusu(nedenler)
            if not ss.onceki_bayrak:  # yeni tetiklenme (kapalı -> açık geçişi)
                ss.form_bayrak_sayisi += 1
                telemetri("kirmizi_bayrak_tetiklendi", "ebeveyn", kod, nedenler=nedenler)
        ss.onceki_bayrak = bool(nedenler)

        st.markdown("**3. Verilen ilaç** (varsa)")
        ilac_verildi = st.toggle("İlaç verdim", key=f"ilac_var_{n}", on_change=_ilk_etkilesim)
        ilac = None
        if ilac_verildi:
            a, b, c, d = st.columns([3, 1.2, 1.2, 1.5])
            ilac_ad = a.text_input("İlaç adı", key=f"ilac_ad_{n}", on_change=_ilk_etkilesim,
                                   placeholder="Örn: Parasetamol şurup")
            doz = b.number_input("Doz", min_value=0.0, step=0.5, value=None,
                                 key=f"doz_{n}", on_change=_ilk_etkilesim)
            birim = c.selectbox("Birim", DOZ_BIRIMLERI, key=f"birim_{n}")
            ss.setdefault(f"saat_{n}", simdi().replace(second=0, microsecond=0).time())
            saat = d.time_input("Saat", key=f"saat_{n}", step=300)
            ilac = {"ad": ilac_ad.strip(), "doz": doz, "birim": birim,
                    "saat": saat.strftime("%H:%M")}

        st.markdown("**4. Kısa not** (isteğe bağlı)")
        notlar = st.text_area("Not", max_chars=280, key=f"not_{n}", on_change=_ilk_etkilesim,
                              label_visibility="collapsed",
                              placeholder="Lütfen isim, telefon gibi kişisel bilgi yazmayınız.")

        if st.button("💾 Kaydet", type="primary", width="stretch"):
            hatalar = []
            if ates is None and not semptomlar and not ilac_verildi and not notlar.strip():
                hatalar.append("Boş kayıt gönderilemez.")
            if ilac_verildi and (not ilac["ad"] or ilac["doz"] is None):
                hatalar.append("İlaç adı ve dozu gerekli.")
            for h in hatalar:
                st.error(h)
            if not hatalar:
                bitis = simdi()
                baslangic = ss.form_ilk_etkilesim or ss.form_acilis
                sure = round((bitis - baslangic).total_seconds(), 1)
                depo.ekle("/kayitlar", {
                    "katilimci": kod,
                    "zaman": bitis.isoformat(timespec="seconds"),
                    "yas_ay": profil.get("yas_ay"),
                    "kilo": profil.get("kilo"),
                    "ates": ates,
                    "semptomlar": semptomlar,
                    "ilac": ilac,
                    "notlar": notlar.strip(),
                    "kirmizi_bayrak": bool(nedenler),
                    "bayrak_nedenleri": nedenler,
                })
                telemetri(
                    "kayit_tamamlandi", "ebeveyn", kod,
                    sure_sn=sure,                                  # ilk etkileşim -> kayıt
                    sure_acilistan_sn=round((bitis - ss.form_acilis).total_seconds(), 1),
                    kirmizi_bayrak_tetiklenme=ss.form_bayrak_sayisi,
                    kayitta_kirmizi_bayrak=bool(nedenler),
                    semptom_sayisi=len(semptomlar),
                    ilac_girildi=bool(ilac),
                )
                ss.son_kayit = {"sure": sure, "bayrak": nedenler}
                # formu sıfırla
                ss.form_no += 1
                ss.form_acilis = simdi()
                ss.form_ilk_etkilesim = None
                ss.form_bayrak_sayisi = 0
                ss.onceki_bayrak = False
                st.rerun()

    if ss.get("son_kayit"):
        st.success("✅ Kaydınız alındı. Hekiminiz muayene öncesinde inceleyebilecek.")
        if ss.son_kayit["bayrak"]:
            st.error("Kayıttaki acil belirtiler nedeniyle lütfen bir sağlık kuruluşuna başvurun.")
        ss.son_kayit = None

    gecmis = kayitlari_getir(kod)
    if not gecmis.empty:
        with st.expander(f"📋 Önceki kayıtlarım ({len(gecmis)})"):
            for _, r in gecmis.iloc[::-1].head(10).iterrows():
                st.markdown(f"- {kayit_satiri(r)}")


# ===========================================================================
# 👩‍⚕️ HEKİM PANELİ
# ===========================================================================
def kayit_satiri(r) -> str:
    parcalar = [r["zaman_dt"].strftime("%d.%m.%Y %H:%M")]
    if pd.notna(r.get("ates")):
        parcalar.append(f"Ateş {r['ates']:.1f} °C")
    if isinstance(r.get("semptomlar"), list) and r["semptomlar"]:
        parcalar.append("Belirti: " + ", ".join(r["semptomlar"]))
    ilac = r.get("ilac")
    if isinstance(ilac, dict) and ilac.get("ad"):
        doz = f"{ilac.get('doz'):g}" if isinstance(ilac.get("doz"), (int, float)) else "?"
        parcalar.append(f"İlaç: {ilac['ad']} {doz} {ilac.get('birim', '')} ({ilac.get('saat', '')})")
    if r.get("notlar"):
        parcalar.append(f"Not: “{r['notlar']}”")
    if r.get("kirmizi_bayrak"):
        parcalar.append("🚨 KIRMIZI BAYRAK")
    return " · ".join(parcalar)


def ozet_metni(kod, profil, df) -> str:
    ates = df["ates"].dropna() if "ates" in df else pd.Series(dtype=float)
    satirlar = [
        f"CHILDNEST KLİNİK ÖZET — Katılımcı {kod}",
        f"Oluşturulma: {simdi():%d.%m.%Y %H:%M}",
        f"Yaş: {yas_metni(profil.get('yas_ay'))} | Kilo: {profil.get('kilo', '—')} kg",
        f"Kayıt sayısı: {len(df)} | Dönem: {df['zaman_dt'].min():%d.%m %H:%M} – "
        f"{df['zaman_dt'].max():%d.%m %H:%M}",
        f"En yüksek ateş: {ates.max():.1f} °C" if not ates.empty else "En yüksek ateş: ölçüm yok",
        f"Kırmızı bayraklı kayıt: {int(df['kirmizi_bayrak'].sum())}",
        "",
        "KRONOLOJİK KAYITLAR (eskiden yeniye):",
    ]
    satirlar += [f"{i}. {kayit_satiri(r)}" for i, (_, r) in enumerate(df.iterrows(), 1)]
    satirlar += ["", "Not: Ebeveyn bildirimidir; araştırma amaçlıdır, tanı/tedavi içermez."]
    return "\n".join(satirlar)


def yazdir_butonu(metin: str, kod: str):
    """Özeti ayrı bir pencerede açıp yazdırma diyaloğunu başlatır (HTML-escape edilir)."""
    guvenli = json.dumps(f"<pre>{html.escape(metin)}</pre>")
    st.iframe(f"""
      <button id="b" style="padding:.5rem 1rem;border-radius:.5rem;border:1px solid #ccc;
              background:#fff;cursor:pointer;font-size:14px">🖨️ Yazdır</button>
      <script>
        document.getElementById('b').onclick = () => {{
          const w = window.open('', '_blank');
          w.document.write('<title>ChildNest {html.escape(kod)}</title>' +
            '<style>body{{font-family:system-ui;font-size:12pt;white-space:pre-wrap}}</style>' + {guvenli});
          w.document.close(); w.focus(); w.print();
        }};
      </script>""", height=48)


def hekim_paneli():
    st.title("👩‍⚕️ Hekim Görünüm Paneli")
    if not sifre_kontrol("doktor_sifresi", "Hekim"):
        return

    df_tumu = kayitlari_getir()
    if df_tumu.empty:
        st.info("Henüz kayıt yok.")
        return

    # Katılımcı listesi: kırmızı bayraklılar ve en son kayıt yapanlar üstte
    ozet = (df_tumu.groupby("katilimci")
            .agg(son=("zaman_dt", "max"), bayrak=("kirmizi_bayrak", "sum"))
            .sort_values(["bayrak", "son"], ascending=False))
    etiket = {k: f"{k}{'  🚨' if r.bayrak else ''}  (son: {r.son:%d.%m %H:%M})"
              for k, r in ozet.iterrows()}
    kod = st.selectbox("Katılımcı", list(etiket), format_func=etiket.get)

    df = df_tumu[df_tumu["katilimci"] == kod]
    profil = depo.oku(f"/katilimcilar/{kod}")

    gorulen = st.session_state.setdefault("gorulen_ozetler", set())
    if kod not in gorulen:
        gorulen.add(kod)
        telemetri("ozet_goruntulendi", "hekim", kod, kayit_sayisi=len(df))

    # --- Klinik Özet Kartı ---
    with st.container(border=True):
        st.subheader(f"🗂️ Klinik Özet Kartı — {kod}")
        son = df.iloc[-1]
        m = st.columns(5)
        m[0].metric("Yaş", yas_metni(profil.get("yas_ay")))
        m[1].metric("Kilo", f"{profil.get('kilo', '—')} kg")
        m[2].metric("Kayıt", len(df))
        m[3].metric("En yüksek ateş",
                    f"{df['ates'].max():.1f} °C" if df["ates"].notna().any() else "—")
        m[4].metric("Kırmızı bayrak", int(df["kirmizi_bayrak"].sum()))

        if son.get("kirmizi_bayrak"):
            st.error("🚨 Son kayıtta kırmızı bayrak: " + ", ".join(son["bayrak_nedenleri"]))

        if df["ates"].notna().sum() >= 2:
            fig = px.line(df.dropna(subset=["ates"]), x="zaman_dt", y="ates", markers=True,
                          labels={"zaman_dt": "", "ates": "°C"}, height=240)
            fig.add_hline(y=ATES_ESIGI, line_dash="dot", line_color="red")
            fig.update_layout(margin=dict(l=0, r=0, t=10, b=0))
            st.plotly_chart(fig, width="stretch")

        st.markdown("**Kronolojik kayıtlar (eskiden yeniye)**")
        for i, (_, r) in enumerate(df.iterrows(), 1):
            st.markdown(f"{i}. {kayit_satiri(r)}")

    # --- Tek tıkla kopyala / yazdır / indir ---
    metin = ozet_metni(kod, profil, df)
    st.markdown("**📋 Özet metni** — sağ üstteki kopyala simgesiyle tek tıkla kopyalayın:")
    st.code(metin, language=None)
    a, b = st.columns([1, 4])
    with a:
        yazdir_butonu(metin, kod)
    b.download_button("⬇️ .txt indir", metin, file_name=f"childnest_{kod}_ozet.txt")


# ===========================================================================
# 📊 ARAŞTIRMACI PANELİ (telemetri + CSV dışa aktarım)
# ===========================================================================
def arastirmaci_paneli():
    st.title("📊 Araştırma Metrikleri")
    if not sifre_kontrol("arastirmaci_sifresi", "Araştırmacı"):
        return

    tel = depo.oku("/telemetri")
    tdf = pd.DataFrame(list(tel.values())) if tel else pd.DataFrame()
    kdf = kayitlari_getir()
    if tdf.empty:
        st.info("Henüz telemetri yok.")
        return

    tam = tdf[tdf["olay"] == "kayit_tamamlandi"]
    bayrak = tdf[tdf["olay"] == "kirmizi_bayrak_tetiklendi"]
    m = st.columns(5)
    m[0].metric("Ebeveyn katılımcı", tdf.loc[tdf["rol"] == "ebeveyn", "katilimci"].nunique())
    m[1].metric("Tamamlanan form", len(tam))
    if not tam.empty:
        m[2].metric("Medyan süre (sn)", f"{tam['sure_sn'].median():.0f}")
        m[3].metric(f"≤{FORM_HEDEF_SN} sn oranı", f"%{(tam['sure_sn'] <= FORM_HEDEF_SN).mean()*100:.0f}")
    m[4].metric("Kırmızı bayrak tetiklenmesi", len(bayrak))

    if not tam.empty:
        st.plotly_chart(px.histogram(tam, x="sure_sn", nbins=20,
                                     labels={"sure_sn": "Tamamlama süresi (sn)"}, height=260),
                        width="stretch")
        st.markdown("**Katılımcı bazında**")
        st.dataframe(tam.groupby("katilimci").agg(
            form=("sure_sn", "size"), medyan_sn=("sure_sn", "median"),
            ort_sn=("sure_sn", "mean"), bayrak_tetiklenme=("kirmizi_bayrak_tetiklenme", "sum"),
        ).round(1))

    st.markdown("**CSV dışa aktarım** (makale analizi için)")
    c1, c2 = st.columns(2)
    tdf_csv = tdf.copy()
    if "nedenler" in tdf_csv:
        tdf_csv["nedenler"] = tdf_csv["nedenler"].apply(
            lambda x: "; ".join(x) if isinstance(x, list) else "")
    c1.download_button("⬇️ telemetri.csv", tdf_csv.sort_values("zaman").to_csv(index=False),
                       file_name="childnest_telemetri.csv", mime="text/csv")
    if not kdf.empty:
        k = kdf.drop(columns=["zaman_dt"]).copy()
        for kol in ("semptomlar", "bayrak_nedenleri"):
            if kol in k:
                k[kol] = k[kol].apply(lambda x: "; ".join(x) if isinstance(x, list) else "")
        if "ilac" in k:
            ilac = k.pop("ilac").apply(lambda x: x if isinstance(x, dict) else {})
            k = k.join(pd.json_normalize(ilac.tolist()).add_prefix("ilac_"))
        c2.download_button("⬇️ kayitlar.csv", k.to_csv(index=False),
                           file_name="childnest_kayitlar.csv", mime="text/csv")


# ---------------------------------------------------------------------------
if rol == "Ebeveyn":
    ebeveyn_paneli()
elif rol == "Hekim":
    hekim_paneli()
else:
    arastirmaci_paneli()
