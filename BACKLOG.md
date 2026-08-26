# BACKLOG.md — Ürün Roadmap ve Gelecek Özellikler

Son Güncelleme: 2026-08-14

## Product Roadmap

### 30 Gün (Eylül 2026) — MVP Stabilization

- [ ] Webhook POST testi — Meta Developer Console
  - URL/Token/field doğrulaması
  - Real mesaj alımı
- [ ] Ollama kurulumu — Docker + Qwen2.5-1.5B
  - LLM intent sınıflandırma
  - Response quality test
- [ ] Alarm sistemi (APScheduler)
  - Sabah özet (08:00)
  - Vade alarmı (3 gün öncesi)
  - Kritik stok bildirimi
- [ ] Delivered/read durum loglama
  - Meta statuses webhook
  - wa_mesaj_log tracking
- [ ] Business Verification
  - Belge yükleme
  - App publish
- [ ] Test DB doldurma
  - Örnek veriler ekleme
  - End-to-end test

### 60 Gün (Ekim 2026) — Features & Analytics

- [ ] Dashboard (web)
  - Şirket bazlı kullanım istatistikleri
  - Mesaj log ekranı
  - Odoo bağlantı status
  - Maliyet raporu (Meta usage)
- [ ] ISG Odoo bağlantısı
  - Account modülü kurulumu veya eksiklik çözümü
  - Çok-şirket desteği test
- [ ] 6 yeni Odoo intent
  - personel_durum (hr.employee)
  - izin_durum (hr.leave)
  - proje_durum (project.project)
  - taksit_durum (payment terms)
  - masraf_durum (hr.expense)
  - bütçe_durum (account.budget, Enterprise)
- [ ] Advanced NLP
  - Bağlamsal sorgular (e.g. "geçen aydaki satış")
  - Multi-turn conversation
  - Follow-up questions

### 90 Gün (Kasım 2026) — Intelligence Layer

- [ ] AI Insights (LLM summary)
  - Satış trendi (metin rapor)
  - En çok satan ürünler
  - Tahsilat performansı
  - Anomali tespiti
- [ ] Anomaly detection
  - Beklenmedik büyük fatura
  - Ani stok düşüşü
  - Olağandışı tahsilat
- [ ] Proaktif bildirimler
  - Otomatik rapor gönderme
  - Aksiyon gerektiren durumlar

### 6 Ay (2027)

- [ ] Subscription modeli (SaaS)
  - Müşteri faturalandırması
  - Kullanım bazlı pricing
  - Plan tipleri (Basic/Pro/Enterprise)
- [ ] Mobile app (iOS/Android)
  - Native WhatsApp integration
  - Push notifications
- [ ] Ecosystem
  - Slack integration (scoped out, future)
  - Telegram bot (scoped out, future)
  - Email reports
- [ ] OpenPyERP entegrasyonu
  - Mevcut OpenPyERP kodu korunur
  - Odoo BI stabil olduktan sonra

---

## Known Issues & Constraints

| ID | Issue | Severity | Status | Notes |
|----|-------|----------|--------|-------|
| 1 | Webhook POST gelmiyor | Critical | Blocking | Meta Console kontrol gerekli |
| 2 | Test DB boş (0 değerler) | High | Pending | Örnek veriler eklenmeli |
| 3 | ISG Odoo bağlantısı | High | Pending | Account modülü eksik veya şifre yok |
| 4 | App unpublished (test mode) | Medium | Pending | Business Verification sonrası publish |
| 5 | Ollama henüz kurulmadı | Medium | Planned | Docker gerekli, 2GB RAM limit |
| 6 | LLM fallback inaktif | Medium | Planned | Ollama kurulumunda aktif olacak |

---

## Design Decisions (Why?)

### 1. Self-hosted LLM (Ollama) vs Cloud API
**Karar:** Ollama  
**Neden:** Finansal veriler müşteri data — cloud API (Anthropic/OpenAI) göndermemek için  
**Trade-off:** Yerel kaynak tüketimi, daha yavaş inference

### 2. Odoo 18 XML-RPC vs OCA Module
**Karar:** XML-RPC (özel client yazılı)  
**Neden:** OCA `mail_gateway_whatsapp` sadece gateway — BI/NLP özelliği yok  
**Trade-off:** Manual entegrasyon, daha kontrollü

### 3. PostgreSQL vs Redis (caching)
**Karar:** PostgreSQL UNIQUE constraint  
**Neden:** Persistent duplicate koruması, server restart'a dayanıklı  
**Trade-off:** Redis daha hızlı olabilir, fakat overkill

### 4. BYOK (Bring Your Own Key) Model
**Karar:** Multi-tenant, şirket başı Meta token  
**Neden:** Müşteri bağımsızlığı, veri privacy  
**Trade-off:** Setup kompleksitesi artar

### 5. Regex → Deneyim Seti → LLM Pipeline
**Karar:** 3-tier cascading NLP  
**Neden:** Maliyet optimizasyonu (LLM sadece fallback), hızlı common queries  
**Trade-off:** Custom deneyim seti kurulması gerekir

---

## Nice-to-Have Features

- [ ] Voice message support (WhatsApp audio)
- [ ] Document extraction (PDF/Excel upload)
- [ ] Multi-language support (İngilizce, Arapça)
- [ ] White-label version (partner resellers)
- [ ] A/B testing framework (NLP improvements)
- [ ] Webhook retry logic (Meta'dan failed POST'lar)
- [ ] Rate limiting per customer
- [ ] API key management dashboard
- [ ] Audit logging (compliance)
- [ ] Dark mode dashboard

---

## Performance Targets

- Webhook response: <2s
- Odoo query: <1s
- LLM inference: <3s (Ollama, 1.5B model)
- Total latency: <6s (user perceives instantly)
- DB query: <100ms (indexed lookups)

---

## Dependencies

- fastapi==0.95.0+
- sqlalchemy==2.0+
- psycopg2-binary (PostgreSQL adapter)
- requests (Odoo XML-RPC)
- python-dotenv
- uvicorn
- ollama (Python SDK) — planlandı

---

## Testing Strategy

- Unit tests: NLP intent detection
- Integration tests: Odoo client
- E2E tests: Webhook → Odoo → Response
- Load tests: 100 concurrent messages/min
- Manual tests: WhatsApp test numbers

---

## Deployment Environments

| Env | Purpose | Odoo Port | Status |
|-----|---------|-----------|--------|
| Test | Development | 8074 | Active |
| ISG | Client demo | 8078 | Inactive (account module) |
| Prod | Live | TBD | Post-verification |

---

## Communication Channels

- GitHub Issues: Feature requests, bugs
- Session docs: Development notes (SESSION.md)
- TASKS.md: Sprint-level tracking
- docs/: Architectural decisions

---

Geliştirici: SHapeloglu  
Proje: WhatsApp BI (DehaWABI)  
Başlangıç: 2026-08-11  
Son Güncelleme: 2026-08-14
