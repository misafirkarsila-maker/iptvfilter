# 📡 IPTV Filter & Multi-Provider Aggregator

<p align="center">
  <a href="#-english"><b>English 🇬🇧</b></a> &nbsp;|&nbsp; <a href="#-türkçe"><b>Türkçe 🇹🇷</b></a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11+-3776AB?style=flat&logo=python&logoColor=white" alt="Python 3.11+">
  <img src="https://img.shields.io/badge/FastAPI-0.110+-009688?style=flat&logo=fastapi&logoColor=white" alt="FastAPI">
  <img src="https://img.shields.io/badge/Docker-Ready-2496ED?style=flat&logo=docker&logoColor=white" alt="Docker">
  <img src="https://img.shields.io/badge/License-MIT-green.svg?style=flat" alt="MIT License">
  <img src="https://img.shields.io/badge/Video%20Traffic-0%25%20(Direct%20302)-success" alt="Zero Video Proxy">
</p>

---

## 🇬🇧 English

A production-ready, ultra-lightweight IPTV management platform and multi-provider aggregator. Merge multiple Xtream Codes providers and M3U playlists into a single clean API & M3U feed, eliminate duplicate channels with smart normalization, customize categories, and filter individual Live TV channels without proxying heavy video streams.

### ⚖️ Legal Disclaimer

> [!IMPORTANT]
> This software is strictly intended for managing, organizing, and filtering IPTV / Xtream playlists that the user has legally obtained or has the legal right to access. **This software does NOT host, stream, scrape, or distribute any media files, video channels, or copyrighted content.** All playback requests are resolved via standard HTTP 302 redirects pointing directly to the original provider's CDN. The developers assume no liability for misuse.

---

### ✨ Key Features

- 🌐 **Multi-Provider Aggregation** — Connect multiple Xtream providers and raw M3U URLs simultaneously. Consolidates Live TV, VOD, and Series into a single unified Xtream API and M3U output.
- 📁 **Smart Country & Language Category Grouping** — Automatically detects country and language prefixes (`TR:`, `DE:`, `FR:`, etc.) and groups categories into neat accordions with instant search and bulk toggle.
- 🔢 **8-Digit Numeric TV PIN** — API passwords are easy-to-type 8-digit numeric PINs designed specifically for smart TV remote controls with custom PIN dialog.
- 📶 **Priority & Failover Ordering** — Reorder providers (▲ / ▼) with a single click. Channels from higher-priority providers take precedence.
- 🧹 **Intelligent Channel Deduplication** — Automatically detects identical channels across multiple providers (stripping prefixes like `TR:`, `[TR]`, `FHD`, `4K`, `HEVC`, and normalizing diacritics) to avoid duplicate clutter while preventing false positives.
- ⚡ **Memory-Safe Streaming M3U Parser** — Ingests 50MB+ M3U playlists in memory-efficient HTTP chunks with zero RAM bloat.
- 📺 **Category & Live TV Channel-Level Filtering** — Enable/disable entire categories or open the channel drawer to search, inspect logos, and toggle individual Live TV channels.
- 🛡️ **Dual Streaming Modes (Zero-Proxy 302 vs Reverse Proxy)** — Choose between lightweight `HTTP 302 Found` direct redirection (zero server bandwidth consumption) or built-in Reverse Video Stream Proxy for restrictive IPTV players.
- 🕒 **Aggregated EPG (XMLTV & Short EPG)** — Generates filtered XMLTV (`/xmltv.php`) and Xtream JSON short EPG (`/player_api.php?action=get_short_epg`) for active channels only.
- 🏗️ **Multi-Arch Docker Ready** — Native `linux/amd64` and `linux/arm64` container images built automatically for VPS, Raspberry Pi, and Apple Silicon.
- 🔒 **Flexible Authentication** — Open access for private home networks or cookie-based password protection for public VPS setups. Fernet AES-128 database credential encryption.
- 🌍 **Bilingual Web Dashboard** — Instant language switching between **Turkish (🇹🇷)** and **English (🇬🇧)** with mobile-first responsive design.

---

### 🚀 Quick Start

#### Option A: Docker Compose (Recommended)

```bash
# 1. Clone repository
git clone https://github.com/misafirkarsila-maker/iptvfilter.git
cd iptvfilter

# 2. Run container (default port: 4788)
docker compose up -d

# 3. Access web dashboard
http://localhost:4788
```

#### Option B: Bare Metal / Native Python (for low-RAM VPS: 128MB - 512MB)

```bash
# 1. Install Python 3.11 & virtual environment
sudo apt update && sudo apt install -y python3 python3-venv git

# 2. Clone and setup
git clone https://github.com/misafirkarsila-maker/iptvfilter.git
cd iptvfilter
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 3. Start server
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

---

### 🌐 Deploying on a NAT VPS with Cloudflare Tunnel (e.g., `iptvfilter.online`)

If your VPS has a NAT IPv4 (shared IP with restricted ports) and you own a domain like `iptvfilter.online`, you can use **Cloudflare Tunnel (`cloudflared`)** for standard HTTPS port 443 with zero port forwarding:

1. Add your domain to Cloudflare (Free plan).
2. Install Cloudflare Tunnel on your VPS:
   ```bash
   curl -L --output cloudflared.deb https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
   sudo dpkg -i cloudflared.deb
   ```
3. Login and route traffic:
   ```bash
   cloudflared tunnel login
   cloudflared tunnel create iptv-tunnel
   cloudflared tunnel route dns iptv-tunnel iptvfilter.online
   cloudflared tunnel run --url http://localhost:8000 iptv-tunnel
   ```
4. Now your dashboard and IPTV API are live on `https://iptvfilter.online` with free automatic SSL!

---

### 📡 API Endpoints

| Endpoint | Description |
| :--- | :--- |
| `GET /player_api.php` | Full Xtream Codes API compatibility (Categories, Streams, EPG, Info) |
| `POST /player_api.php` | Support for players requesting via HTTP POST (e.g. IPTV Smarters) |
| `GET /playlist.m3u` / `/get.php` | Unified and deduplicated M3U / M3U Plus playlist |
| `GET /xmltv.php` | Filtered XMLTV electronic program guide (EPG) |
| `GET /live/{u}/{p}/{id}.ts` | Live TV direct playback redirect (HTTP 302) |
| `GET /movie/{u}/{p}/{id}.mp4`| VOD movie direct playback redirect |
| `GET /series/{u}/{p}/{id}.mp4`| Series episode direct playback redirect |
| `GET /{u}/{p}/{id}` | Generic direct playback router for modern players (TiviMate) |
| `GET /health` | Healthcheck endpoint for Docker / monitoring |

---

<br>

## 🇹🇷 Türkçe

Üretim standartlarında, son derece hafif ve modern bir IPTV çalma listesi yönetim ve birleştirme (multi-provider aggregation) platformu. Birden fazla Xtream sağlayıcısını ve M3U linkini tek bir yayında birleştirir, duplicate (çift) kanalları gelişmiş normalizasyonla eler, kategori ve kanal bazlı filtreleme sağlar. Sunucunuzdan asla video trafiği geçirmez.

### ⚖️ Yasal Uyarı

> [!IMPORTANT]
> Bu yazılım yalnızca kullanıcının yasal olarak erişim hakkına sahip olduğu IPTV ve Xtream servislerini yönetmek, filtrelemek ve düzenlemek amacıyla geliştirilmiştir. **Yazılım herhangi bir video içeriği, kanal, yayın veya abonelik barındırmaz ve dağıtmaz.** Tüm video oynatma istekleri `HTTP 302 Found` yönlendirmesiyle doğrudan sağlayıcının kendi CDN adresine yönlendirilir. Yazılımın hukuka aykırı amaçlarla kullanılmasından tamamen kullanıcı sorumludur.

---

### ✨ Temel Özellikler

- 🌐 **Multi-Provider Aggregation** — Birden fazla Xtream sağlayıcısını ve saf M3U linkini aynı anda aktif edin; Canlı TV, Film (VOD) ve Dizi içeriklerini tek bir Xtream API ve M3U çıktısında birleştirin.
- 📁 **Akıllı Ülke & Dil Gruplaması (Accordion)** — Kategori isimlerindeki ülke ve dil takılarını (`TR:`, `DE:`, `FR:`, vb.) otomatik tespit eder; kategorileri akordeon gruplara ayırır, anlık arama ve grup bazlı toplu aç/kapat imkanı sunar.
- 🔢 **8 Haneli Sayısal TV PIN** — API şifreleri, akıllı televizyon kumandalarıyla rahatça girilebilmesi için tamamen rakamlardan oluşan 8 haneli PIN formatına yükseltildi. İsterseniz özel PIN belirleyebilirsiniz.
- 📶 **Sağlayıcı Önceliği (Priority Sıralaması)** — Panelden sağlayıcıların öncelik sırasını (▲ / ▼) tek tıkla değiştirin. Üst sıradaki sağlayıcının kanalları önceliklidir.
- 🧹 **Akıllı Duplicate Kanal Yönetimi** — Aynı kanal birden fazla sağlayıcıda varsa otomatik tespit edilip elenir. `TR:`, `[TR]`, `FHD`, `4K`, `HEVC` gibi takılar ve Türkçe karakter farkları temizlenir.
- ⚡ **Bellek Dostu Akışkan M3U Parser** — 50MB+ devasa M3U dosyalarını RAM tüketmeden HTTP streaming ile satır satır işler.
- 📺 **Kategori & Live TV Kanal Düzeyinde Filtreleme** — İstemediğiniz kategorileri kapatın veya Canlı TV kategorilerinin içine girerek logoları ve anlık arama motoruyla tek tek kanalları açıp kapatın.
- 🛡️ **Çift Yayın Akış Modu (302 Direct vs Reverse Stream Proxy)** — İster sunucu trafiği harcamayan hafif `HTTP 302` doğrudan yönlendirmeyi, ister kısıtlayıcı oynatıcılar için sunucu üzerinden aktaran Reverse Video Proxy modunu tek tıkla kullanın.
- 🕒 **Birleşik EPG (XMLTV & Short EPG)** — Yalnızca seçtiğiniz aktif kanalların EPG bilgileri `/xmltv.php` ve `/player_api.php?action=get_short_epg` çıktısına dahil edilir.
- 🏗️ **Multi-Arch Docker Desteği** — Raspberry Pi ve Apple Silicon dahil tüm ortamlar için otomatik `linux/amd64` ve `linux/arm64` imajları.
- 🔒 **Esnek Güvenlik** — Yerel ağda şifresiz kullanım veya internete açık sunucularda şifre korumalı panel. Sağlayıcı şifreleri Fernet AES-128 ile veritabanında şifreli saklanır.
- 🌍 **Çift Dil Desteği (i18n)** — Tek tıkla **Türkçe (🇹🇷)** ve **İngilizce (🇬🇧)** arasında geçiş yapılabilen mobil uyumlu şık web paneli.

---

### 🚀 Hızlı Kurulum

#### Yöntem A: Docker Compose ile (Önerilen)

```bash
git clone https://github.com/misafirkarsila-maker/iptvfilter.git
cd iptvfilter
docker compose up -d
```

Tarayıcınızdan `http://<sunucu-ip>:4788` adresine gidin.

#### Yöntem B: Düşük RAM'li VPS'lerde Saf Python ile (128MB - 512MB)

```bash
sudo apt update && sudo apt install -y python3 python3-venv git
git clone https://github.com/misafirkarsila-maker/iptvfilter.git
cd iptvfilter
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

---

### 🌐 NAT VPS & Alan Adı Kurulumu (`iptvfilter.online`)

Sunucunuz paylaşımlı NAT IPv4 adresine sahipse, **Cloudflare Tunnel (`cloudflared`)** kullanarak port açma derdi olmadan `https://iptvfilter.online` adresini standart 443 portu ve ücretsiz SSL ile bağlayabilirsiniz:

1. `iptvfilter.online` alan adınızı Cloudflare'e ekleyin.
2. Sunucunuza `cloudflared` kurun:
   ```bash
   curl -L --output cloudflared.deb https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
   sudo dpkg -i cloudflared.deb
   ```
3. Tüneli bağlayın:
   ```bash
   cloudflared tunnel login
   cloudflared tunnel create iptv-tunnel
   cloudflared tunnel route dns iptv-tunnel iptvfilter.online
   cloudflared tunnel run --url http://localhost:8000 iptv-tunnel
   ```
4. Artık paneliniz ve IPTV API adresiniz doğrudan `https://iptvfilter.online` üzerinden dünya standartlarında SSL ile çalışacaktır!

---

### 📄 Lisans

MIT License © 2026