# ChildNest — Pilot Kullanılabilirlik Çalışması

Uzaktan pediatrik semptom ve ilaç kaydı için **araştırma prototipi**.
Ebeveyn-hekim iletişimini ve kullanılabilirliği değerlendiren pilot çalışma (25–30 ebeveyn, 5–10 hekim) için hazırlanmıştır.

> ⚠️ Bu platform bilimsel araştırma ve kullanılabilirlik testi amacıyla hazırlanmıştır. Tanı veya tedavi önerisi sunmaz; acil durumlarda en yakın sağlık kuruluşuna başvurunuz.

## Paneller

| Rol | Erişim | İçerik |
|---|---|---|
| Ebeveyn | Katılımcı kodu (örn. `A01`) + onam onayı | Yaş (ay/yıl), kilo; semptom ve ilaç kayıt formu; kırmızı bayrak uyarısı + "Okudum, anladım"; hekimin "incelendi" bildirimi; SUS anketi |
| Hekim | Hekim kodu (`H1`) + kendi şifresi | Yalnızca **kendisine atanmış** katılımcılar; Klinik Özet Kartı, 🆕 incelenmemiş kayıtlar, "incelendi olarak işaretle", kopyala / yazdır / .txt; SUS anketi |
| Araştırmacı | `arastirmaci_sifresi` | Kullanılabilirlik, güvenlik ve iletişim metrikleri; 3 CSV dışa aktarım |

Ad-soyad, TC kimlik no, doğum tarihi, telefon **toplanmaz**. Hekimin ebeveyne gönderebileceği mesajlar sabit ve klinik içermeyen 3 seçenekle sınırlıdır (serbest metin yok).

**Test kodları:** `Z` ile başlayan kodlar (`Z01`, `Z99`) deneme içindir. Her hekim bunları görür, ancak araştırmacı panelindeki metriklere ve CSV dosyalarına **dahil edilmez** (isteğe bağlı açılabilir).

## Kişisel linkler

Katılımcılara ve hekimlere doğrudan doğru ekranı açan link verin:

- Ebeveyn: `https://<uygulama-adresi>/?rol=ebeveyn&kod=A01`
- Hekim: `https://<uygulama-adresi>/?rol=hekim&hekim=H1`

Linkler şifre içermez; hekim şifresini yine kendisi girer.

## Kırmızı bayrak kuralları (`app.py` başındaki sabitler)

- Ateş ≥ 39.0 °C
- 3 aydan küçük bebekte ateş ≥ 38.0 °C
- Acil belirtilerden herhangi biri: nefes darlığı, bilinç değişikliği, havale, morarma, solmayan döküntü, ense sertliği, sıvı alamama/idrar yok

Uyarı, kayıt beklenmeden alan değiştiği anda gösterilir.

## Telemetri tanımları (makale için)

`/telemetri` altında olay bazlı, anonim kayıtlar tutulur. Her kayıtta yalnızca katılımcı/hekim kodu ve rastgele bir oturum kimliği bulunur.

| Olay | Rol | Alanlar |
|---|---|---|
| `oturum_acildi` | ebeveyn / hekim | `hekim` |
| `kirmizi_bayrak_tetiklendi` | ebeveyn | `nedenler`. Uyarının kapalıdan açığa her geçişi bir tetiklenme sayılır |
| `kirmizi_bayrak_onaylandi` | ebeveyn | `onay_suresi_sn`: uyarının çıkmasından "Okudum, anladım"a kadar geçen süre |
| `kayit_tamamlandi` | ebeveyn | `sure_sn`: ilk alana dokunma → Kaydet. `sure_acilistan_sn`: form açılışı → Kaydet. Ayrıca `kirmizi_bayrak_tetiklenme`, `kayitta_kirmizi_bayrak`, `kirmizi_bayrak_onaylandi`, `semptom_sayisi`, `ilac_girildi` |
| `ozet_goruntulendi` | hekim | `hekim`, `kayit_sayisi`. Hekimin bir katılımcı özetini oturumda ilk açışı |
| `kayit_incelendi` | hekim | `hekim`, `kayit_id`, `kayit_zamani`, `gecikme_dk`: kaydın girilmesinden "incelendi"ye kadar geçen süre. Her kayıt için bir satır |
| `inceleme_goruldu` | ebeveyn | `inceleme_zamani`, `hekim`. Ebeveynin bildirimi bir oturumda ilk görüşü |
| `sus_tamamlandi` | ebeveyn / hekim | `sus_puani` (0–100) |

**SUS (System Usability Scale):** 10 madde, 1–5 Likert. Puan = Σ(tek maddeler: yanıt−1; çift maddeler: 5−yanıt) × 2,5. Uygulamadaki madde metinleri geçerli Türkçe uyarlamaya yakın bir çeviridir. Makalede atıf yaptığınız uyarlamanın metniyle karşılaştırıp gerekirse `SUS_MADDELERI` listesini güncelleyin.

Araştırmacı panelinden `childnest_telemetri.csv`, `childnest_kayitlar.csv` ve `childnest_sus.csv` dosyaları indirilebilir.

## Kurulum

```bash
pip install -r requirements.txt
streamlit run app.py
```

`.streamlit/secrets.toml` (Streamlit Cloud'da: App settings → Secrets):

```toml
arastirmaci_sifresi = "..."

database_url = "https://<proje>-default-rtdb.<bölge>.firebasedatabase.app/"
textkey = '''{ ...Firebase servis hesabı JSON... }'''   # yoksa veri yerel data/ klasörüne yazılır

[hekimler.H1]
sifre = "..."
katilimcilar = ["A01", "A02", "A03"]

[hekimler.H2]
sifre = "..."
katilimcilar = ["B01", "B02"]
# katilimcilar = ["*"]  -> tüm katılımcıları görür
```

`textkey` tanımlı değilse uygulama **yerel demo modunda** çalışır (`data/childnest_yerel.json`). Streamlit Cloud'da bu dosya kalıcı değildir; pilot çalışmada mutlaka Firebase kullanın.

## Firebase güvenlik notu

Uygulama sunucu tarafında Admin SDK kullanır; tarayıcının veritabanına doğrudan erişmesi gerekmez. Realtime Database'i **kilitli modda** açın veya kuralları şöyle ayarlayın:

```json
{ "rules": { ".read": false, ".write": false } }
```
