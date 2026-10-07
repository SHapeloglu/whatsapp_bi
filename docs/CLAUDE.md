# CLAUDE.md — Proje Talimatları

## Proje Özeti

WhatsApp Business Intelligence (whatsapp_bi / DehaWABI)
Stack: FastAPI + PostgreSQL + Odoo 18 XML-RPC + Self-hosted LLM (Ollama)
Amaç: Türkçe doğal dil sorguları ile Odoo finansal verileri WhatsApp'tan sorgulanabilir

## Teknik Özellikler

- Webhook: HMAC-SHA256 doğrulaması (2026-08-11 OK)
- Duplicate Koruması: PostgreSQL UNIQUE constraint (2026-08-13 OK)
- Medya Reddi: Fotoğraf/ses gelince Türkçe cevap (2026-08-14 OK)
- NLP: Regex → Deneyim seti → LLM fallback (Ollama planlandı)
- Multi-tenant: Şirket bazlı Meta hesapları

## Sunucu Bilgisi

Port 9000: WhatsApp BI (FastAPI)
Port 8074: Odoo Test (aktif)
Port 5432: PostgreSQL
Port 11434: Ollama (Docker, planlandı)

## Komutlar

Loglar: journalctl -u whatsapp-bi -f
Restart: systemctl restart whatsapp-bi
Nginx: tail -30 /var/log/nginx/access.log
Odoo test: curl -H "X-API-Key: $ADMIN_API_KEY" http://127.0.0.1:9000/odoo-sirketler   # anahtar .env'de
