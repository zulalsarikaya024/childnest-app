"""
ChildNest — Pilot Kullanılabilirlik Çalışması Sürümü

Bu uygulama bilimsel bir araştırma (kullanılabilirlik ve ebeveyn-hekim iletişimi
pilot çalışması) için hazırlanmıştır. Tanı veya tedavi önerisi sunmaz.

Veri modeli (kimliksiz / takma adlı):
  /katilimcilar/{kod}    -> {yas_ay, kilo, guncelleme}
  /kayitlar/{push_id}    -> semptom ve ilaç kayıtları
  /incelemeler/{kod}     -> hekimin son "incelendi" bildirimi {hekim, zaman, mesaj}
  /sus/{rol}_{kimlik}    -> System Usability Scale yanıtları ve puanı
  /telemetri/{push_id}   -> anonim kullanım olayları (süre, kırmızı bayrak, inceleme...)

Z ile başlayan katılımcı kodları (Z01, Z99...) test kodudur; analize/CSV'ye girmez.
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
TEST_ONEKI = "Z"                             # Z01, Z99 -> test kodu, analiz dışı
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

# Hekimin ebeveyne gösterebileceği sabit, klinik içermeyen mesajlar (serbest metin yok)
INCELEME_MESAJLARI = [
    "(mesaj yok)",
    "Kayıtlarınız için teşekkürler.",
    "Muayenede birlikte değerlendireceğiz.",
    "Kayıt tutmaya devam etmeniz faydalı olur.",
]

# System Usability Scale (Brooke, 1996). Makalede yayımlanmış geçerli Türkçe uyarlamanın
# madde metinlerini kullanın; buradaki ifadeler ona yakın bir çeviridir.
SUS_MADDELERI = [
    "Bu uygulamayı sık sık kullanmak isterim.",
    "Uygulamayı gereksiz yere karmaşık buldum.",
    "Uygulamanın kullanımı kolaydı.",
    "Bu uygulamayı kullanabilmek için teknik birinin desteğine ihtiyaç duyarım.",
    "Uygulamadaki işlevlerin iyi bir şekilde bir araya getirildiğini düşünüyorum.",
    "Uygulamada çok fazla tutarsızlık olduğunu düşünüyorum.",
    "Çoğu kişinin bu uygulamayı çok çabuk öğreneceğini düşünüyorum.",
    "Uygulamayı kullanmayı çok zahmetli buldum.",
    "Uygulamayı kullanırken kendime çok güvendim.",
    "Bu uygulamayı kullanmadan önce birçok şey öğrenmem gerekti.",
]

UYARI_METNI = (
    "Bu platform **bilimsel araştırma ve kullanılabilirlik testi** amacıyla hazırlanmıştır. "
    "**Tanı veya tedavi önerisi sunmaz;** acil durumlarda en yakın sağlık kuruluşuna "
    "başvurunuz (☎️ **112**)."
)


def simdi() -> dt.datetime:
    return dt.datetime.now(TZ)


def zaman_cevir(deger) -> pd.Timestamp:
    return pd.Timestamp(deger).tz_convert(TZ)


def test_kodu_mu(kod) -> bool:
    return str(kod or "").upper().startswith(TEST_ONEKI)


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

    def __init__(self, anahtar: dict, url: str):
        import firebase_admin
        from firebase_admin import credentials, db

        if not firebase_admin._apps:
            firebase_admin.initialize_app(credentials.Certificate(anahtar), {"databaseURL": url})
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


class AnahtarHatasi(Exception):
    pass


def firebase_anahtari_coz(ham) -> dict:
    """Secrets'taki textkey'i sözlüğe çevirir; kopyala-yapıştırda sık görülen bozulmaları onarır.
    Hata mesajları anahtarın içeriğini ASLA göstermez, yalnızca konum/ipucu verir."""
    if hasattr(ham, "keys"):                      # [textkey] tablo olarak girilmişse
        return {k: ham[k] for k in ham.keys()}
    metin = str(ham).strip()
    if "BURAYA" in metin:
        raise AnahtarHatasi("textkey içinde hâlâ 'BURAYA-...' yer tutucusu duruyor; "
                            "JSON dosyasının içeriğini yapıştırın.")
    # Akıllı tırnaklar (“ ” ‘ ’) ve görünmez boşluklar -> düz karakter
    metin = (metin.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")
             .replace(" ", " ").replace("﻿", ""))
    if not metin.startswith("{"):
        raise AnahtarHatasi("textkey '{' ile başlamalı. JSON dosyasının tamamını kopyalayın.")
    if not metin.endswith("}"):
        raise AnahtarHatasi("textkey '}' ile bitmeli. JSON eksik kopyalanmış olabilir.")
    try:
        # strict=False: \"\"\" kullanıldığında private_key içindeki gerçek satır sonlarını kabul eder
        veri = json.loads(metin, strict=False)
    except json.JSONDecodeError as e:
        raise AnahtarHatasi(f"textkey geçerli JSON değil (satır {e.lineno}, sütun {e.colno}: "
                            f"{e.msg}). Dosyayı yeniden kopyalayıp yapıştırın.") from None
    eksik = [k for k in ("type", "project_id", "private_key", "client_email") if k not in veri]
    if eksik:
        raise AnahtarHatasi(f"Anahtarda eksik alan(lar): {', '.join(eksik)}. "
                            "Firebase'den indirilen hizmet hesabı dosyasını kullanın.")
    return veri


@st.cache_resource
def depo_al():
    key = _secret("textkey")
    if key:
        url = _secret("database_url", "https://childnest-e3bab-default-rtdb.firebaseio.com/")
        return FirebaseDepo(firebase_anahtari_coz(key), url)
    return YerelDepo()


try:
    depo = depo_al()
except AnahtarHatasi as e:
    st.error(f"🔑 **Firebase anahtarı okunamadı.** {e}\n\n"
             "Düzeltmek için: Manage app → Settings → Secrets → `textkey` alanı.")
    st.stop()
except Exception as e:
    st.error(f"🔑 **Firebase bağlantısı kurulamadı** ({type(e).__name__}). "
             "Secrets'taki `textkey` ve `database_url` değerlerini kontrol edin.")
    st.stop()


# ---------------------------------------------------------------------------
# TELEMETRİ (anonim: yalnızca katılımcı/hekim kodu + oturum kimliği + olay)
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
    if not veri:
        return pd.DataFrame()
    df = pd.DataFrame([{**v, "id": k} for k, v in veri.items()])
    if katilimci:
        df = df[df["katilimci"] == katilimci]
        if df.empty:
            return df
    df["zaman_dt"] = pd.to_datetime(df["zaman"], utc=True).dt.tz_convert(TZ)
    return df.sort_values("zaman_dt").reset_index(drop=True)


def sus_puani(cevaplar: list[int]) -> float:
    """Tek maddeler: (yanıt-1), çift maddeler: (5-yanıt); toplam x 2.5 -> 0-100."""
    return sum((c - 1) if i % 2 == 0 else (5 - c) for i, c in enumerate(cevaplar)) * 2.5


def sus_anketi(rol: str, kimlik: str, katilimci: str | None = None, **ek):
    yol = f"/sus/{rol}_{kimlik}"
    mevcut = depo.oku(yol)
    baslik = "📝 Kısa değerlendirme anketi (10 soru, ~2 dk)"
    with st.expander(baslik + (" — ✅ tamamlandı" if mevcut else ""), expanded=False):
        if mevcut:
            st.success(f"Teşekkürler! Anketi {zaman_cevir(mevcut['zaman']):%d.%m.%Y} "
                       "tarihinde tamamladınız.")
            return
        st.caption("Her ifade için: 1 = Kesinlikle katılmıyorum · 5 = Kesinlikle katılıyorum")
        with st.form(f"sus_{rol}"):
            cevaplar = [
                st.radio(f"{i}. {madde}", [1, 2, 3, 4, 5], index=None, horizontal=True,
                         key=f"sus_{rol}_{i}")
                for i, madde in enumerate(SUS_MADDELERI, 1)
            ]
            if st.form_submit_button("Anketi gönder", type="primary"):
                if None in cevaplar:
                    st.error("Lütfen tüm soruları yanıtlayın.")
                else:
                    puan = sus_puani(cevaplar)
                    depo.yaz(yol, {"rol": rol, "kimlik": kimlik, "cevaplar": cevaplar,
                                   "puan": puan, "zaman": simdi().isoformat(timespec="seconds")})
                    telemetri("sus_tamamlandi", rol, katilimci, sus_puani=puan, **ek)
                    st.rerun()


# ---------------------------------------------------------------------------
# GİRİŞ EKRANI ORTAK ÖĞELER
# ---------------------------------------------------------------------------
st.warning(UYARI_METNI, icon="⚠️")

ROLLER = ["Ebeveyn", "Hekim", "Araştırmacı"]
_url_rol = {"ebeveyn": 0, "hekim": 1, "arastirmaci": 2}.get(
    str(st.query_params.get("rol", "")).lower(), 0)
st.sidebar.title("🧪 ChildNest Pilot")
rol = st.sidebar.radio("Rolünüzü seçin:", ROLLER, index=_url_rol)
st.sidebar.caption(f"Veri deposu: {depo.ad}")


def oturumu_kapat():
    for k in list(st.session_state.keys()):
        if k != "oturum_id":
            del st.session_state[k]
    st.rerun()


def sifre_kontrol(secret_adi: str, etiket: str) -> bool:
    """Araştırmacı paneli için basit erişim şifresi (st.secrets içinde)."""
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
    ss = st.session_state

    # --- 1) Katılımcı girişi (kimlik bilgisi yok, yalnızca kod) ---
    if not ss.get("katilimci"):
        with st.form("katilimci_giris"):
            kod = st.text_input("Katılımcı Kodu", value=st.query_params.get("kod", ""),
                                placeholder="Örn: A01",
                                help="Araştırma ekibinin size verdiği kod.").strip().upper()
            onam = st.checkbox("Bilgilendirilmiş onam formunu okudum ve imzaladım.")
            if st.form_submit_button("Giriş", type="primary"):
                if not KOD_DESENI.match(kod):
                    st.error("Kod biçimi geçersiz. Örnek: A01")
                elif not onam:
                    st.error("Devam etmek için onam kutusunu işaretleyin.")
                else:
                    ss.katilimci = kod
                    telemetri("oturum_acildi", "ebeveyn", kod)
                    st.rerun()
        return

    kod = ss.katilimci
    profil = depo.oku(f"/katilimcilar/{kod}")

    c1, c2 = st.columns([4, 1])
    c1.info(f"Katılımcı: **{kod}**{' (TEST)' if test_kodu_mu(kod) else ''} · "
            f"Çocuğun yaşı: **{yas_metni(profil.get('yas_ay'))}** · "
            f"Kilo: **{profil.get('kilo', '—')} kg**")
    if c2.button("Çıkış"):
        oturumu_kapat()

    # --- Hekim inceleme bildirimi (iletişimin ebeveyne dönen tarafı) ---
    gecmis = kayitlari_getir(kod)
    inceleme = depo.oku(f"/incelemeler/{kod}")
    if inceleme:
        t = zaman_cevir(inceleme["zaman"])
        mesaj = f"🩺 Hekiminiz kayıtlarınızı **{t:%d.%m.%Y %H:%M}** tarihinde inceledi. ✓"
        if inceleme.get("mesaj"):
            mesaj += f"\n\n💬 “{inceleme['mesaj']}”"
        st.success(mesaj)
        if not gecmis.empty and gecmis["zaman_dt"].max() > t:
            st.caption("Bu tarihten sonraki kayıtlarınız henüz incelenmedi.")
        gorulen = ss.setdefault("gorulen_incelemeler", set())
        if inceleme["zaman"] not in gorulen:
            gorulen.add(inceleme["zaman"])
            telemetri("inceleme_goruldu", "ebeveyn", kod, inceleme_zamani=inceleme["zaman"],
                      hekim=inceleme.get("hekim", ""))

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

    if not gecmis.empty:
        with st.expander(f"📋 Önceki kayıtlarım ({len(gecmis)})"):
            for _, r in gecmis.iloc[::-1].head(10).iterrows():
                st.markdown(f"- {kayit_satiri(r)}")
        sus_anketi("ebeveyn", kod, katilimci=kod)


def _ilk_etkilesim():
    """Herhangi bir form alanına ilk dokunulduğu an (tamamlama süresinin başlangıcı)."""
    if st.session_state.get("form_ilk_etkilesim") is None:
        st.session_state.form_ilk_etkilesim = simdi()


def _formu_sifirla():
    ss = st.session_state
    ss.form_no = ss.get("form_no", -1) + 1   # yeni widget anahtarları -> boş form
    ss.form_acilis = simdi()                 # form ekrana geldiği an
    ss.form_ilk_etkilesim = None
    ss.form_bayrak_sayisi = 0                # bu form doldurulurken kaç kez tetiklendi
    ss.onceki_bayrak = False
    ss.bayrak_zamani = None
    ss.bayrak_onaylandi = False


def kayit_formu(kod, profil):
    ss = st.session_state
    if "form_no" not in ss:
        _formu_sifirla()
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
            if not ss.onceki_bayrak:  # yeni tetiklenme (kapalı -> açık geçişi)
                ss.form_bayrak_sayisi += 1
                ss.bayrak_zamani = simdi()
                ss.bayrak_onaylandi = False
                telemetri("kirmizi_bayrak_tetiklendi", "ebeveyn", kod, nedenler=nedenler)
            ss.onceki_bayrak = True
            kirmizi_bayrak_kutusu(nedenler)
            if ss.bayrak_onaylandi:
                st.caption("✓ Uyarıyı okuduğunuzu belirttiniz.")
            elif st.button("✓ Okudum, anladım", key=f"bayrak_onay_{n}_{ss.form_bayrak_sayisi}"):
                ss.bayrak_onaylandi = True
                telemetri("kirmizi_bayrak_onaylandi", "ebeveyn", kod,
                          onay_suresi_sn=round((simdi() - ss.bayrak_zamani).total_seconds(), 1))
                st.rerun()
        else:
            ss.onceki_bayrak = False

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
                    "bayrak_onaylandi": ss.bayrak_onaylandi if nedenler else None,
                })
                telemetri(
                    "kayit_tamamlandi", "ebeveyn", kod,
                    sure_sn=sure,                                  # ilk etkileşim -> kayıt
                    sure_acilistan_sn=round((bitis - ss.form_acilis).total_seconds(), 1),
                    kirmizi_bayrak_tetiklenme=ss.form_bayrak_sayisi,
                    kayitta_kirmizi_bayrak=bool(nedenler),
                    kirmizi_bayrak_onaylandi=ss.bayrak_onaylandi if nedenler else None,
                    semptom_sayisi=len(semptomlar),
                    ilac_girildi=bool(ilac),
                )
                ss.son_kayit = {"sure": sure, "bayrak": nedenler}
                _formu_sifirla()
                st.rerun()

    if ss.get("son_kayit"):
        st.success("✅ Kaydınız alındı. Hekiminiz muayene öncesinde inceleyebilecek.")
        if ss.son_kayit["bayrak"]:
            st.error("Kayıttaki acil belirtiler nedeniyle lütfen bir sağlık kuruluşuna başvurun.")
        ss.son_kayit = None


# ===========================================================================
# 👩‍⚕️ HEKİM PANELİ
# ===========================================================================
def hekim_hesaplari() -> dict:
    """secrets: [hekimler.H1] sifre="..." katilimcilar=["A01","A02"]  ("*" = tümü).
    Geriye dönük uyum: yalnızca doktor_sifresi varsa H0 kodlu, herkesi gören hesap."""
    hesaplar = {}
    try:
        for hk, h in dict(st.secrets["hekimler"]).items():
            hesaplar[str(hk).upper()] = {
                "sifre": str(h["sifre"]),
                "katilimcilar": [str(x).upper() for x in (h["katilimcilar"] if "katilimcilar" in h else [])],
            }
    except Exception:
        pass
    eski = _secret("doktor_sifresi")
    if eski and "H0" not in hesaplar:
        hesaplar["H0"] = {"sifre": str(eski), "katilimcilar": ["*"]}
    return hesaplar


def hekim_girisi():
    ss = st.session_state
    if ss.get("hekim"):
        return ss.hekim
    hesaplar = hekim_hesaplari()
    if not hesaplar:
        st.error("Bu panel kapalı: secrets içinde `[hekimler]` tanımlı değil.")
        return None
    with st.form("hekim_giris"):
        hk = st.text_input("Hekim kodu", value=st.query_params.get("hekim", ""),
                           placeholder="Örn: H1").strip().upper()
        sifre = st.text_input("Şifre", type="password")
        if st.form_submit_button("Giriş", type="primary"):
            h = hesaplar.get(hk)
            if h and hmac.compare_digest(sifre.encode(), h["sifre"].encode()):
                ss.hekim = {"kod": hk, "katilimcilar": h["katilimcilar"]}
                telemetri("oturum_acildi", "hekim", hekim=hk)
                st.rerun()
            st.error("Hekim kodu veya şifre hatalı.")
    return None


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
    hekim = hekim_girisi()
    if not hekim:
        return
    hk = hekim["kod"]
    izinli = hekim["katilimcilar"]

    c1, c2 = st.columns([4, 1])
    c1.caption(f"Giriş: **{hk}** · "
               + ("tüm katılımcılar" if "*" in izinli else f"{len(izinli)} atanmış katılımcı"))
    if c2.button("Çıkış"):
        oturumu_kapat()

    df_tumu = kayitlari_getir()
    if not df_tumu.empty:
        gorebilir = df_tumu["katilimci"].map(
            lambda k: "*" in izinli or k in izinli or test_kodu_mu(k))
        df_tumu = df_tumu[gorebilir]
    if df_tumu.empty:
        st.info("Size atanmış katılımcıların henüz kaydı yok.")
        sus_anketi("hekim", hk, hekim=hk)
        return

    incelemeler = depo.oku("/incelemeler")

    def son_inceleme(k):
        return zaman_cevir(incelemeler[k]["zaman"]) if k in incelemeler else None

    # Katılımcı listesi: incelenmemiş + kırmızı bayraklı kayıtlar üstte
    satirlar = []
    for k, g in df_tumu.groupby("katilimci"):
        t = son_inceleme(k)
        yeni = g if t is None else g[g["zaman_dt"] > t]
        satirlar.append({"kod": k, "son": g["zaman_dt"].max(), "yeni": len(yeni),
                         "yeni_bayrak": int(yeni["kirmizi_bayrak"].sum())})
    ozet = pd.DataFrame(satirlar).sort_values(["yeni_bayrak", "yeni", "son"], ascending=False)
    etiket = {
        r.kod: f"{r.kod}{'  🚨' if r.yeni_bayrak else ''}"
               f"{f'  🆕 {r.yeni} yeni' if r.yeni else '  ✓'}  (son: {r.son:%d.%m %H:%M})"
        for r in ozet.itertuples()
    }
    # Liste yeniden sıralansa da (örn. "incelendi" sonrası) seçili katılımcı korunur
    secenekler = list(etiket)
    onceki = st.session_state.get("hekim_secili")
    kod = st.selectbox("Katılımcı", secenekler, format_func=etiket.get,
                       index=secenekler.index(onceki) if onceki in secenekler else 0)
    st.session_state.hekim_secili = kod

    df = df_tumu[df_tumu["katilimci"] == kod]
    profil = depo.oku(f"/katilimcilar/{kod}")

    gorulen = st.session_state.setdefault("gorulen_ozetler", set())
    if kod not in gorulen:
        gorulen.add(kod)
        telemetri("ozet_goruntulendi", "hekim", kod, hekim=hk, kayit_sayisi=len(df))

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

        t = son_inceleme(kod)
        st.markdown("**Kronolojik kayıtlar (eskiden yeniye)**")
        for i, (_, r) in enumerate(df.iterrows(), 1):
            yeni = t is None or r["zaman_dt"] > t
            st.markdown(f"{i}. {'🆕 ' if yeni else ''}{kayit_satiri(r)}")

    # --- "İncelendi" bildirimi: ebeveyn görür, gecikme telemetriye yazılır ---
    with st.container(border=True):
        st.markdown("**✓ İnceleme bildirimi** — ebeveyn, kayıtlarının incelendiğini görür")
        if t is not None:
            st.caption(f"Son inceleme: {t:%d.%m.%Y %H:%M} ({incelemeler[kod].get('hekim', '')})")
        yeni_df = df if t is None else df[df["zaman_dt"] > t]
        if yeni_df.empty:
            st.success("Tüm kayıtlar incelendi.")
        else:
            mesaj = st.selectbox("Ebeveyne gösterilecek kısa mesaj (isteğe bağlı)",
                                 INCELEME_MESAJLARI)
            if st.button(f"✓ {len(yeni_df)} yeni kaydı incelendi olarak işaretle", type="primary"):
                an = simdi()
                depo.yaz(f"/incelemeler/{kod}", {
                    "hekim": hk, "zaman": an.isoformat(timespec="seconds"),
                    "mesaj": "" if mesaj == INCELEME_MESAJLARI[0] else mesaj,
                })
                for _, r in yeni_df.iterrows():
                    telemetri("kayit_incelendi", "hekim", kod, hekim=hk, kayit_id=r["id"],
                              kayit_zamani=r["zaman"],
                              gecikme_dk=round((an - r["zaman_dt"]).total_seconds() / 60, 1))
                st.rerun()

    # --- Tek tıkla kopyala / yazdır / indir ---
    metin = ozet_metni(kod, profil, df)
    st.markdown("**📋 Özet metni** — sağ üstteki kopyala simgesiyle tek tıkla kopyalayın:")
    st.code(metin, language=None)
    a, b = st.columns([1, 4])
    with a:
        yazdir_butonu(metin, kod)
    b.download_button("⬇️ .txt indir", metin, file_name=f"childnest_{kod}_ozet.txt")

    st.divider()
    sus_anketi("hekim", hk, hekim=hk)


# ===========================================================================
# 📊 ARAŞTIRMACI PANELİ (telemetri + CSV dışa aktarım)
# ===========================================================================
def _liste_metne(df, kolonlar):
    for kol in kolonlar:
        if kol in df:
            df[kol] = df[kol].apply(lambda x: "; ".join(map(str, x)) if isinstance(x, list) else x)
    return df


def arastirmaci_paneli():
    st.title("📊 Araştırma Metrikleri")
    if not sifre_kontrol("arastirmaci_sifresi", "Araştırmacı"):
        return

    testleri_dahil_et = st.toggle(f"Test kodlarını ({TEST_ONEKI}…) dahil et", value=False)

    tel = depo.oku("/telemetri")
    tdf = pd.DataFrame(list(tel.values())) if tel else pd.DataFrame()
    kdf = kayitlari_getir()
    sus = depo.oku("/sus")
    sdf = pd.DataFrame(list(sus.values())) if sus else pd.DataFrame()

    if not testleri_dahil_et:
        if not tdf.empty:
            tdf = tdf[~tdf["katilimci"].map(test_kodu_mu)]
        if not kdf.empty:
            kdf = kdf[~kdf["katilimci"].map(test_kodu_mu)]
        if not sdf.empty:
            sdf = sdf[~((sdf["rol"] == "ebeveyn") & sdf["kimlik"].map(test_kodu_mu))]
    if tdf.empty:
        st.info("Henüz telemetri yok.")
        return

    def olay(ad):
        return tdf[tdf["olay"] == ad]

    tam = olay("kayit_tamamlandi")
    bayrak = olay("kirmizi_bayrak_tetiklendi")
    onay = olay("kirmizi_bayrak_onaylandi")
    incelendi = olay("kayit_incelendi")

    st.markdown("#### Kullanılabilirlik")
    m = st.columns(5)
    m[0].metric("Ebeveyn katılımcı", tdf.loc[tdf["rol"] == "ebeveyn", "katilimci"].nunique())
    m[1].metric("Tamamlanan form", len(tam))
    if not tam.empty:
        m[2].metric("Medyan süre (sn)", f"{tam['sure_sn'].median():.0f}")
        m[3].metric(f"≤{FORM_HEDEF_SN} sn oranı",
                    f"%{(tam['sure_sn'] <= FORM_HEDEF_SN).mean() * 100:.0f}")
    def sus_ozet(r):
        p = sdf[sdf["rol"] == r]["puan"] if not sdf.empty else pd.Series(dtype=float)
        return f"{p.mean():.1f} (n={len(p)})" if len(p) else "—"

    m[4].metric("SUS ebeveyn (ort.)", sus_ozet("ebeveyn"))

    st.markdown("#### Güvenlik ve iletişim")
    m = st.columns(5)
    m[0].metric("Kırmızı bayrak tetiklenmesi", len(bayrak))
    m[1].metric("Uyarı onay oranı",
                f"%{len(onay) / len(bayrak) * 100:.0f}" if len(bayrak) else "—")
    m[2].metric("İncelenen kayıt oranı",
                f"%{incelendi['kayit_id'].nunique() / len(kdf) * 100:.0f}"
                if len(kdf) and not incelendi.empty else "—")
    m[3].metric("Medyan inceleme gecikmesi",
                f"{incelendi['gecikme_dk'].median() / 60:.1f} saat" if not incelendi.empty else "—")
    m[4].metric("SUS hekim (ort.)", sus_ozet("hekim"))

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
    c1, c2, c3 = st.columns(3)
    t_csv = _liste_metne(tdf.copy(), ["nedenler"])
    c1.download_button("⬇️ telemetri.csv", t_csv.sort_values("zaman").to_csv(index=False),
                       file_name="childnest_telemetri.csv", mime="text/csv")
    if not kdf.empty:
        k = _liste_metne(kdf.drop(columns=["zaman_dt"]).reset_index(drop=True),
                         ["semptomlar", "bayrak_nedenleri"])
        if "ilac" in k:
            ilac = k.pop("ilac").apply(lambda x: x if isinstance(x, dict) else {})
            k = k.join(pd.json_normalize(ilac.tolist()).add_prefix("ilac_"))
        c2.download_button("⬇️ kayitlar.csv", k.to_csv(index=False),
                           file_name="childnest_kayitlar.csv", mime="text/csv")
    if not sdf.empty:
        s = sdf.copy()
        cev = pd.DataFrame(s.pop("cevaplar").tolist(),
                           columns=[f"m{i}" for i in range(1, 11)], index=s.index)
        c3.download_button("⬇️ sus.csv", s.join(cev).to_csv(index=False),
                           file_name="childnest_sus.csv", mime="text/csv")


# ---------------------------------------------------------------------------
if rol == "Ebeveyn":
    ebeveyn_paneli()
elif rol == "Hekim":
    hekim_paneli()
else:
    arastirmaci_paneli()
