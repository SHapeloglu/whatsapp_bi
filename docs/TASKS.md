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
