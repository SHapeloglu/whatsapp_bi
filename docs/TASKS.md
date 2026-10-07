# TASKS.md — WhatsApp BI Görev Listesi

Son güncelleme: 2026-08-14

## ✅ Tamamlananlar

- [x] HMAC imza doğrulaması (2026-08-11)
- [x] Duplicate mesaj koruması (2026-08-13)
- [x] Medya mesajı reddi (2026-08-14)
- [x] Odoo 18 XML-RPC client
- [x] NLP regex pipeline
- [x] PostgreSQL setup

## 🔄 Devam Edenler

### 🔴 BLOCKING

- [ ] **🔴 Yönetim uçları kimliksiz ve internete açık** (2026-10-07) — `/kullanici-ekle`, `/kullanici-sil`, `/kullanicilar`, `/sirket-ayar-kaydet`, `/sirket-token-yenile`, `/mesaj-listesi`, `/maliyet-raporu`, `/odoo-sirketler` auth içermiyor; servis `0.0.0.0:9000` + `whatsappbi.odoodanismanlik.com` üzerinden açık, `/docs` dışarıdan görülüyor. Herkes numara ekleyip finans verisi sorgulayabilir / token değiştirebilir. Yap: `--host 127.0.0.1`, yönetim uçlarına API anahtarı (`Depends`), `FastAPI(docs_url=None, redoc_url=None)`. (`/root/ISLISTESI.md` #53)
- [ ] Webhook POST testi — Meta Console kontrol (2026-08-14)
  1. Webhook URL doğru mu kaydedilmiş?
  2. Verify Token eşleşiyor mu (openpyerp_verify_2026)?
  3. Messages field subscribe'dı mı?
  4. Test numarası recipient listesinde mi?
  5. Console Test → nginx log 200 OK görülmeli

### 🔵 Sıradaki (30. Gün)

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
| 4 | Webhook POST | 🔴 BLOCKING |
