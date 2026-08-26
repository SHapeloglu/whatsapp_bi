# ARCHITECTURE.md — Sistem Mimarisi

## Genel Akış

WhatsApp (Kullanıcı)
  → Meta Cloud API (POST webhook)
  → FastAPI port 9000
     - HMAC doğrulama
     - Duplicate kontrol
     - Medya mesajı reddi
     - NLP (Regex → LLM)
  → Odoo XML-RPC port 8074
  → PostgreSQL
  → Yanıt WhatsApp'a

## Bileşenler

### 1. Webhook Handler (whatsapp_bi.py)
- POST /webhook → HMAC doğrulama
- Mesaj loop → duplicate check → type check → NLP → Odoo query
- Yanıt via background task

### 2. Odoo Client (odoo_client.py)
- XML-RPC over HTTP (port 8074)
- Multi-tenant (odoo_sirket_id per şirket)
- Intents: özet, banka, cari, fatura, satış, stok, vb.

### 3. NLP Pipeline (wa_nlp.py)
- Regex intent detection
- Deneyim seti fallback
- LLM fallback (Ollama, Docker, planlandı)

### 4. Veritabanı (PostgreSQL)
- wa_islenmis_mesaj: msg.id UNIQUE constraint
- wa_mesaj_log: tarih, intent, yanıt, durum
- wa_sirket_ayar: Meta token per şirket
- wa_kullanici: WhatsApp → Odoo user mapping

## Güvenlik

- HMAC-SHA256 webhook doğrulaması ✅ (2026-08-11)
- Token per şirket (BYOK model)
- Duplicate mesaj koruması ✅ (2026-08-13)
- Medya mesajı reddi ✅ (2026-08-14)

## Deployment

- systemd: /etc/systemd/system/whatsapp-bi.service
- Nginx reverse proxy + SSL (Let's Encrypt)
- PostgreSQL persistent DB
- Odoo test instance (:8074) aktif
- Ollama (Docker, :11434) planlandı
