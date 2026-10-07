# WhatsApp Business Intelligence (DehaWABI)

Odoo 18 finansal verilerini WhatsApp'tan Türkçe doğal dil sorguları ile sorgulanabilir hale getiren FastAPI uygulaması.

## Özellikler

- HMAC-SHA256 webhook doğrulaması (`WA_APP_SECRET` yoksa istekler reddedilir)
- Yönetim uçları `X-API-Key` başlığıyla korunur (`ADMIN_API_KEY`); Swagger `/docs` kapalı
- Duplicate mesaj koruması (PostgreSQL)
- Medya mesajı reddi (foto/ses gelince Türkçe cevap)
- Multi-tenant (şirket bazlı Meta hesapları)
- NLP Pipeline (regex → deneyim seti → LLM)
- Odoo 18 XML-RPC entegrasyonu

## Stack

- Backend: FastAPI (Python 3.9+)
- DB: PostgreSQL
- ERP: Odoo 18 (XML-RPC)
- NLP: Qwen2.5-1.5B (Ollama, Docker) - planlandı
- Web: Nginx + SSL

## Kurulum

git clone https://github.com/SHapeloglu/whatsapp_bi.git
cd whatsapp_bi
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
nano .env
systemctl start whatsapp-bi

## Yönetim uçları

`/kullanici-ekle`, `/kullanici-sil`, `/kullanicilar`, `/sirket-ayar-kaydet`, `/sirket-token-yenile`, `/odoo-sirketler`, `/mesaj-listesi`, `/maliyet-raporu` — hepsi `X-API-Key: <ADMIN_API_KEY>` başlığı ister (yoksa 401; `.env`'de anahtar tanımlı değilse 503). Açık uçlar: `/webhook` (GET doğrulama, POST HMAC) ve `/saglik`.

```bash
curl -H "X-API-Key: $ADMIN_API_KEY" http://127.0.0.1:9000/kullanicilar
```

Servis yalnız `127.0.0.1:9000`'de dinler; dış erişim nginx üzerinden.

## Webhook (Meta Console)

1. URL: https://yourdomain.com/webhook
2. Verify Token: .env'deki WA_VERIFY_TOKEN
3. Subscribe: messages field
4. Test numarası: recipient listesine ekle

## Belgeler

- docs/CLAUDE.md - Claude AI talimatları
- docs/SESSION.md - Oturum özeti
- docs/ARCHITECTURE.md - Sistem mimarisi
- docs/TASKS.md - Görev listesi

## Durum (2026-08-14)

Tamamlandı:
- HMAC güvenliği
- Duplicate koruması
- Medya mesajı reddi
- Odoo entegrasyonu (test)

Devam Ediyor:
- Webhook POST testi (Meta Console)
- Ollama kurulumu
- Alarm sistemi

Geliştirici: SHapeloglu
Son Güncelleme: 2026-08-14
