# TASKS.md — WhatsApp BI Görev Listesi

Son güncelleme: 2026-08-14

## ✅ Tamamlananlar

- [x] Yönetim uçlarına `X-API-Key` (`ADMIN_API_KEY`), `/docs`/`/openapi.json` kapatıldı, servis `127.0.0.1:9000`'e alındı, HMAC anahtar yoksa reddediyor (2026-10-07)
- [x] Meta webhook GET doğrulaması `hub.mode`/`hub.verify_token`/`hub.challenge` adlarıyla düzeltildi (2026-10-07)
- [x] HMAC imza doğrulaması (2026-08-11)
- [x] Duplicate mesaj koruması (2026-08-13)
- [x] Medya mesajı reddi (2026-08-14)
- [x] Odoo 18 XML-RPC client
- [x] NLP regex pipeline
- [x] PostgreSQL setup

## 🔄 Devam Edenler

### 🔴 BLOCKING

- [ ] Webhook POST testi — Meta Console kontrol (2026-08-14). **2026-10-07:** GET doğrulama hiç çalışmıyordu (kod `hub_mode` bekliyordu, Meta `hub.mode` gönderir) → düzeltildi, sunucudan doğru token ile 200 + challenge dönüyor. Meta Console'da URL'i yeniden "Verify and save" yap.
  1. Webhook URL doğru mu kaydedilmiş?
  2. Verify Token eşleşiyor mu (openpyerp_verify_2026)?
  3. Messages field subscribe'dı mı?
  4. Test numarası recipient listesinde mi?
  5. Console Test → nginx log 200 OK görülmeli

### 🔵 Sıradaki (30. Gün)

- [ ] İlk gerçek mesajda doğrula: `webhook_mesaj` istek kapsamlı `db` oturumunu `mesaj_isle_async` arka plan görevine geçiriyor; FastAPI ≥0.106'da `get_db`'nin `finally: db.close()`'u arka plan görevinden **önce** çalışır. Hata görülürse görev içinde yeni `SessionLocal()` aç. (2026-10-07)
- [ ] Ollama kurulumu — Docker + Qwen2.5-1.5B
- [ ] Alarm sistemi — APScheduler (vade, kritik stok)
- [ ] Delivered/read durum loglama
- [ ] Business Verification — Meta'ya belge yükle

## 🐛 Bilinen Hatalar

| # | Hata | Durum |
|---|------|-------|
| 1 | HMAC | ✅ Kapatıldı |
| 2 | Duplicate | ✅ Kapatıldı |
| 3 | Medya Reddi | ✅ Kapatıldı |
| 4 | Webhook GET doğrulama parametre adları (`hub.mode`) | ✅ Kapatıldı (2026-10-07) — Meta tarafında yeniden doğrulama bekliyor |
| 5 | Yönetim uçları kimliksiz, servis 0.0.0.0, `/docs` açık | ✅ Kapatıldı (2026-10-07) |
| 6 | `WA_APP_SECRET` boşsa HMAC geçiyordu | ✅ Kapatıldı (2026-10-07) |
