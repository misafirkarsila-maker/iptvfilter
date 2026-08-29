# Xtream Filter — IPTV Liste Yönetim ve Multi-Provider Filtreleme Uygulaması

Docker üzerinde çalışan, video trafiğini sunucudan geçirmeyen, birden fazla Xtream sağlayıcısını öncelik sırasına ve kategori filtrelerine göre tek bir yayında birleştiren (aggregation) açık kaynaklı IPTV yönetim uygulaması.

---

## ⚖️ Yasal Uyarı

Bu yazılım yalnızca kullanıcının yasal olarak erişim hakkına sahip olduğu IPTV/Xtream servislerini yönetmek, filtrelemek ve düzenlemek amacıyla geliştirilmiştir. Yalnızca yasal ve lisanslı IPTV sağlayıcılarının kullanılması gerekir. Yazılım herhangi bir IPTV içeriği, kanal, yayın veya abonelik sağlamaz. Telif hakkıyla korunan içeriklere yetkisiz erişim veya dağıtım yapılması amaçlanmamaktadır. Yazılımın hukuka aykırı amaçlarla kullanılmasından kullanıcı sorumludur.

---

## ⚡ Hızlı Kurulum (Tek Dosya)

```bash
# 1. Compose dosyasını indir
curl -O https://raw.githubusercontent.com/misafirkarsila-maker/xtream-playlist-manager/main/docker-compose.yml

# 2. Çalıştır (tüm default'lar yaml içinde, sıfır konfigürasyonla hazır)
docker compose up -d

# 3. Panel'e eriş
# http://<sunucu-ip>:8000
# Tailscale / Yerel Ağ: http://<tailscale-ip>:8000
```

> **Not:** İlk açılışta `ENCRYPTION_KEY` ve `API_PASSWORD` otomatik olarak üretilip güvenle saklanır. Web paneli varsayılan olarak şifresiz açılır; yerel ağ veya Tailscale üzerinde doğrudan kullanabilirsiniz. İsterseniz panel üzerinden tek tıkla şifreli koruma aktif edebilirsiniz.

---

## 🎯 Temel Özellikler

- 🌐 **Multi-Provider Aggregation** — Birden fazla Xtream sağlayıcısını aynı anda aktif edin; Live TV, VOD ve Series içeriklerini tek bir Xtream API veya M3U çıktısında birleştirin.
- 📶 **Sağlayıcı Önceliği (Priority / Order)** — Web panelinden sağlayıcıların öncelik sırasını (▲ / ▼) değiştirin. Üst sıradaki sağlayıcılar öncelikli değerlendirilir (gelecekteki fallback mekanizmalarıyla tam uyumlu).
- 🧹 **Akıllı Duplicate Kanal Yönetimi** — Aynı kanal birden fazla sağlayıcıda varsa tekilleştirilir, duplicate yayınlar elenir. `TR:`, `[TR]`, `FHD`, `4K`, `HEVC` gibi takılar ve Türkçe karakter farkları güvenli biçimde normalize edilir; yanlış pozitiflere (örn: `BEIN SPORTS 1` ile `BEIN SPORTS 2`) yol açmaz.
- 📺 **Kategori Filtreleme** — Live TV / VOD / Series için kategori bazlı aktif/pasif seçim yapın; gereksiz binlerce kanalı eleyerek cihazlarınızı hızlandırın.
- ⚡ **Bulk Toggle** — Kategori başlıklarında tek tıkla "Tümünü Seç / Tümünü Kaldır" (HTMX destekli).
- 🕒 **Birleşik EPG (XMLTV & Short EPG)** — Sadece seçtiğiniz ve filtrelenmiş aktif kanalların EPG kayıtları `xmltv.php` ve `player_api.php?action=get_short_epg` çıktısına dahil edilir.
- 📱 **TiviMate & Xtream Codes Standart Uyumluluğu** — IPTV oynatıcınızda tek bir Xtream hesabı ile birleştirilmiş tüm listeye bağlanın.
- 🚫 **Proxy YOK (Direct Stream Redirection)** — Video akışı sunucunuzun bant genişliğini tüketmez. Oynatıcı istekleri HTTP 302 ile doğrudan sağlayıcının CDN adresine yönlendirilir.
- 🔐 **Esnek ve Güvenli Kimlik Doğrulama** — `PANEL_PASSWORD` boşsa yerel ağlarda şifresiz kolay kullanım; doluysa cookie korumalı oturum. Xtream API şifresi otomatik oluşturulur ve panelde gösterilir. Sağlayıcı şifreleri Fernet (AES-128) ile veritabanında şifreli saklanır.
- 🕐 **Otomatik Günlük Senkronizasyon** — APScheduler ile her gün 03:00'te tüm sağlayıcılar otomatik güncellenir.
- 🐳 **Docker Ready** — Kalıcı `./data:/app/data` volume yapısı ve yerleşik healthcheck ile üretime hazır.

---

## 🔧 Konfigürasyon (Environment Variables)

Varsayılan değerler otomatik yönetilir. İhtiyaç halinde `docker compose` veya `.env` üzerinden override edilebilir:

| Değişken | Açıklama | Varsayılan |
|----------|----------|------------|
| `APP_HOST` | Sunucu dinleme adresi | `0.0.0.0` |
| `APP_PORT` | Sunucu portu | `8000` |
| `DATABASE_URL` | SQLite veritabanı yolu | `sqlite:////app/data/app.db` |
| `API_USER` | IPTV oynatıcı kullanıcı adı | `myuser` |
| `API_PASSWORD` | IPTV oynatıcı şifresi | (Otomatik üretilir, panelde gösterilir) |
| `PANEL_PASSWORD` | Web paneli giriş şifresi | (Boş = Şifresiz / Doğrudan erişim) |
| `ENCRYPTION_KEY` | Sağlayıcı şifreleri için Fernet anahtarı | (İlk çalıştırmada otomatik üretilir) |
| `SYNC_CRON` | Günlük senkronizasyon cron ifadesi | `0 3 * * *` |
| `LOG_LEVEL` | Log ayrıntı düzeyi | `INFO` |

---

## 🚀 Kullanım Adımları

1. **Paneli Açın:** Tarayıcınızdan `http://<sunucu-ip>:8000` adresine gidin.
2. **Sağlayıcıları Ekleyin:** "+ Yeni IPTV Sağlayıcı Ekle" formundan Xtream sağlayıcılarınızı ekleyin.
3. **Öncelik Sırasını Belirleyin:** Sağlayıcı kartlarındaki ▲ / ▼ butonlarını kullanarak hangi sağlayıcının öncelikli olacağını belirleyin.
4. **Kategorileri Filtreleyin:** "Kategorileri Yönet" butonuna tıklayarak izlemek istediğiniz kategorileri seçin, istemediklerinizi kapatın.
5. **IPTV Oynatıcınıza Ekleyin:**
   - Paneldeki **Xtream API Bağlantı Kartı**'ndan bilgilerinizi alın:
     - **Sunucu:** `http://<sunucu-ip>:8000`
     - **Kullanıcı:** `myuser`
     - **Şifre:** Panelde görünen API şifresi
   - Veya doğrudan **M3U** / **EPG** bağlantısını kopyalayıp oynatıcınıza yapıştırın.

---

## 📡 Desteklenen API Uç Noktaları

| Endpoint | Açıklama |
|----------|----------|
| `/player_api.php` | Tam Xtream Codes API uyumluluğu (kategoriler, yayınlar, EPG) |
| `/xmltv.php` | Tekilleştirilmiş kanallara ait XMLTV formatında EPG çıktısı |
| `/get.php?type=live` | Birleştirilmiş ve filtrelenmiş M3U çalma listesi |
| `/live/{user}/{pass}/{stream_id}.ts` | TiviMate / Xtream doğrudan yayın oynatma yönlendirmesi (HTTP 302) |
| `/movie/{user}/{pass}/{stream_id}.mp4` | VOD doğrudan oynatma yönlendirmesi |
| `/series/{user}/{pass}/{stream_id}` | Dizi doğrudan oynatma yönlendirmesi |
| `/health` | Docker sağlık kontrolü (Healthcheck) |

---

## 🐳 Docker & Kalıcılık

- **Volume:** `./data:/app/data` (Veritabanı, ayarlar ve şifreleme anahtarı bu dizinde saklanır).
- **Restart İlkesi:** `unless-stopped`

```bash
docker compose up -d
```

---

## 📄 Lisans

MIT