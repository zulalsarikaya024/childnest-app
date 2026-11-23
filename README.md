# ChildNest — Pilot Kullanılabilirlik Çalışması

Uzaktan pediatrik semptom ve ilaç kaydı için **araştırma prototipi**.
Ebeveyn-hekim iletişimini ve kullanılabilirliği değerlendiren pilot çalışma (25–30 ebeveyn, 5–10 hekim) için hazırlanmıştır.

> ⚠️ Bu platform bilimsel araştırma ve kullanılabilirlik testi amacıyla hazırlanmıştır. Tanı veya tedavi önerisi sunmaz; acil durumlarda en yakın sağlık kuruluşuna başvurunuz.

## Paneller

| Rol | Erişim | İçerik |
|---|---|---|
| Ebeveyn | Katılımcı kodu (örn. `A01`) + onam onayı | Yaş (ay/yıl), kilo; semptom ve ilaç kayıt formu; kırmızı bayrak uyarısı |
| Hekim | `doktor_sifresi` | Katılımcı başına Klinik Özet Kartı, ateş grafiği, kopyala / yazdır / .txt indir |
| Araştırmacı | `arastirmaci_sifresi` | Tamamlama süresi, kırmızı bayrak sayıları, CSV dışa aktarım |

Ad-soyad, TC kimlik no, doğum tarihi, telefon **toplanmaz**.

## Kırmızı bayrak kuralları (`app.py` başındaki sabitler)

- Ateş ≥ 39.0 °C
- 3 aydan küçük bebekte ateş ≥ 38.0 °C
- Acil belirtilerden herhangi biri: nefes darlığı, bilinç değişikliği, havale, morarma, solmayan döküntü, ense sertliği, sıvı alamama/idrar yok

Uyarı, kayıt beklenmeden alan değiştiği anda gösterilir.

## Telemetri tanımları (makale için)

`/telemetri` altında olay bazlı, anonim (yalnızca katılımcı kodu + rastgele oturum kimliği):

| Olay | Alanlar |
|---|---|
| `oturum_acildi` | — |
| `kirmizi_bayrak_tetiklendi` | `nedenler` — uyarının kapalıdan açığa her geçişi bir tetiklenmedir |
| `kayit_tamamlandi` | `sure_sn` (ilk alana dokunma → Kaydet), `sure_acilistan_sn` (form ekrana geldi → Kaydet), `kirmizi_bayrak_tetiklenme`, `kayitta_kirmizi_bayrak`, `semptom_sayisi`, `ilac_girildi` |
| `ozet_goruntulendi` | Hekimin bir katılımcı özetini oturumda ilk açışı, `kayit_sayisi` |

Araştırmacı panelinden `childnest_telemetri.csv` ve `childnest_kayitlar.csv` indirilebilir.

## Kurulum

```bash
pip install -r requirements.txt
streamlit run app.py
```

`.streamlit/secrets.toml` (Streamlit Cloud'da: App settings → Secrets):

```toml
doktor_sifresi = "..."
arastirmaci_sifresi = "..."
textkey = '''{ ...Firebase servis hesabı JSON... }'''   # yoksa veri yerel data/ klasörüne yazılır
database_url = "https://<proje>-default-rtdb.firebaseio.com/"
```

`textkey` tanımlı değilse uygulama **yerel demo modunda** çalışır (`data/childnest_yerel.json`).

## Firebase güvenlik notu

Uygulama sunucu tarafında Admin SDK kullanır; tarayıcıdan doğrudan veritabanına erişim gerekmez. Realtime Database kurallarını tamamen kapatın:

```json
{ "rules": { ".read": false, ".write": false } }
```
