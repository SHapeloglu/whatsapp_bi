"""
╔══════════════════════════════════════════════════════════════╗
║               WhatsApp BI  v1.0                              ║
║  Meta Cloud API webhook → CariMatik API entegrasyonu         ║
╠══════════════════════════════════════════════════════════════╣
║  Kurulum : pip install -r requirements_wa.txt                ║
║  Çalıştır: uvicorn whatsapp_bi:app --reload --port 9000      ║
║  Webhook : POST https://sizin-domain.com/webhook             ║
╚══════════════════════════════════════════════════════════════╝

Akış:
  1. Meta → POST /webhook  (müşteriden gelen mesaj)
  2. wa_no → wa_kullanici tablosundan sirket_id bul
  3. Mesaj içeriğini parse et → hangi API endpoint?
  4. CariMatik API'yi çağır → veriyi al
  5. Cevabı WhatsApp'a gönder
  6. wa_mesaj_log'a yaz (faturalandırma için)
"""

# ── Standart kütüphane ────────────────────────────────────────
import os
import re
import json
import logging
from datetime import datetime, date, timedelta
from typing import Optional

# ── FastAPI ───────────────────────────────────────────────────
from fastapi import FastAPI, Request, HTTPException, Depends, BackgroundTasks
from fastapi.responses import PlainTextResponse

# ── HTTP istemcisi ────────────────────────────────────────────
import httpx

# ── Veritabanı ────────────────────────────────────────────────
from sqlalchemy import (
    create_engine, Column, Integer, String,
    Boolean, DateTime, Numeric, Enum, Text,
    ForeignKey, func
)
from sqlalchemy.orm import declarative_base, Session, sessionmaker

# ── Config ────────────────────────────────────────────────────
try:
    import config as cfg
    MYSQL_URI = (
        f"mysql+pymysql://{cfg.DB_USER}:{cfg.DB_PASSWORD}"
        f"@{cfg.DB_HOST}:{cfg.DB_PORT}/{cfg.DB_NAME}?charset=utf8mb4"
    )
except ImportError:
    MYSQL_URI = os.getenv(
        "DATABASE_URL",
        "mysql+pymysql://root:sifre@localhost/muhasebe?charset=utf8mb4"
    )

# ── Ortam değişkenleri ────────────────────────────────────────
# Meta Developer Console → App → WhatsApp → API Setup'tan alınır
# WA_TOKEN ve WA_PHONE_ID artık global değil — her şirket kendi bilgilerini girer
VERIFY_TOKEN      = os.getenv("WA_VERIFY_TOKEN", "carimatik_verify_2024")  # Webhook doğrulama
# OpenPyERP API bağlantısı
# Flask uygulaması ile aynı sunucuda: /api/v2 prefix
OPENPYERP_API_URL = os.getenv("OPENPYERP_API_URL", "http://localhost:5000")
OPENPYERP_API_KEY = os.getenv("OPENPYERP_API_KEY", "")   # X-API-Key header (opsiyonel)
OPENPYERP_EMAIL   = os.getenv("OPENPYERP_EMAIL", "admin@firma.com")
OPENPYERP_SIFRE   = os.getenv("OPENPYERP_SIFRE", "")

# Geriye dönük uyumluluk — eski isimlerden de okunur
if not OPENPYERP_API_URL:
    OPENPYERP_API_URL = os.getenv("CARIMATIK_API_URL", "http://localhost:5000")
if not OPENPYERP_EMAIL:
    OPENPYERP_EMAIL = os.getenv("CARIMATIK_USER", "admin@firma.com")
if not OPENPYERP_SIFRE:
    OPENPYERP_SIFRE = os.getenv("CARIMATIK_PASS", "")

# ── Loglama ───────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger("wa_bi")

# ══════════════════════════════════════════════════════════════
#  VERİTABANI — sadece 2 yeni tablo, mevcut DB'ye eklenir
# ══════════════════════════════════════════════════════════════

engine = create_engine(MYSQL_URI, pool_pre_ping=True, pool_recycle=3600)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


class WaSirketAyar(Base):
    """
    Her müşteri şirketin kendi Meta hesap bilgileri.
    BYOK modeli: müşteri kendi token'ını girer, mesaj maliyeti ona ait.
    Token 60 günde bir yenilenmeli — token_son_guncelleme ile takip edilir.
    """
    __tablename__ = "wa_sirket_ayar"

    id                   = Column(Integer, primary_key=True, autoincrement=True)
    sirket_id            = Column(Integer, ForeignKey("sirket.id", use_alter=True), nullable=False, unique=True)
    wa_phone_id          = Column(String(50))   # Meta Phone Number ID
    wa_business_id       = Column(String(50))   # Meta Business Account ID
    wa_token             = Column(Text)          # Access Token (hassas veri)
    wa_aktif             = Column(Boolean, default=False)
    token_son_guncelleme = Column(DateTime)      # Token yenilenme tarihi
    olusturma            = Column(DateTime, default=datetime.now)
    guncelleme           = Column(DateTime, onupdate=datetime.now)


class WaKullanici(Base):
    """
    WhatsApp numarasını CariMatik şirket/kullanıcısına bağlar.
    Yeni müşteri ilk mesaj attığında buraya kayıt düşülür (veya admin ekler).
    """
    __tablename__ = "wa_kullanici"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    wa_no      = Column(String(20), nullable=False, unique=True)  # +905321234567
    sirket_id  = Column(Integer, ForeignKey("sirket.id", use_alter=True), nullable=False)
    aktif      = Column(Boolean, default=True)
    olusturma  = Column(DateTime, default=datetime.now)


class WaMesajLog(Base):
    """
    Her gelen/giden mesaj buraya yazılır.
    Faturalandırma ve kullanım analizi için.
    """
    __tablename__ = "wa_mesaj_log"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    sirket_id   = Column(Integer, ForeignKey("sirket.id", use_alter=True), nullable=False)
    wa_no       = Column(String(20))
    yon         = Column(Enum("GELEN", "GIDEN", name="wa_mesaj_yon"), nullable=False)
    mesaj_tipi  = Column(Enum("servis", "utility", "marketing", name="wa_mesaj_tipi"), default="servis")
    mesaj_ozet  = Column(String(200))          # İlk 200 karakter
    ucretli     = Column(Boolean, default=False)
    meta_usd    = Column(Numeric(10, 6), default=0)  # Gerçek Meta maliyeti
    tarih       = Column(DateTime, default=datetime.now)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def tablolari_olustur():
    """Sadece wa_ tablolarını oluşturur, mevcut tablolara dokunmaz."""
    WaSirketAyar.__table__.create(bind=engine, checkfirst=True)
    WaKullanici.__table__.create(bind=engine, checkfirst=True)
    WaMesajLog.__table__.create(bind=engine, checkfirst=True)
    log.info("wa_ tabloları hazır")


# ══════════════════════════════════════════════════════════════
#  CARİMATİK API İSTEMCİSİ
# ══════════════════════════════════════════════════════════════

_jwt_token: Optional[str] = None   # Bellekte JWT cache
_token_suresi: Optional[datetime] = None  # Token bitiş zamanı


async def openpyerp_token() -> str:
    """
    OpenPyERP API'den JWT token alır, 7.5 saatte bir yeniler.
    Değişiklikler CariMatik'e göre:
      - Endpoint: /login → /api/v2/login
      - Body: form-data → JSON {email, sifre}
      - API Key varsa doğrudan kullan, token almaya gerek yok
    """
    global _jwt_token, _token_suresi

    # API Key varsa token gerekmez
    if OPENPYERP_API_KEY:
        return ""

    # Cache geçerliyse döndür (7.5 saat = 450 dakika)
    if _jwt_token and _token_suresi and datetime.now() < _token_suresi:
        return _jwt_token

    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{OPENPYERP_API_URL}/api/v2/login",
            json={"email": OPENPYERP_EMAIL, "sifre": OPENPYERP_SIFRE},
            timeout=10.0,
        )
        r.raise_for_status()
        _jwt_token    = r.json()["access_token"]
        _token_suresi = datetime.now().replace(
            hour=datetime.now().hour,
            minute=datetime.now().minute,
            second=datetime.now().second
        )
        from datetime import timedelta as _td
        _token_suresi = datetime.now() + _td(minutes=450)
        log.info("OpenPyERP API token alındı")
        return _jwt_token


def _api_headers(token: str) -> dict:
    """Auth header'larını oluşturur — API Key veya JWT."""
    if OPENPYERP_API_KEY:
        return {"X-API-Key": OPENPYERP_API_KEY}
    return {"Authorization": f"Bearer {token}"}


async def openpyerp_get(endpoint: str, params: dict = None) -> dict:
    """
    OpenPyERP API'ye GET isteği atar.
    Endpoint'ler artık /api/v2 prefix'li.
    """
    global _jwt_token, _token_suresi
    token = await openpyerp_token()

    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{OPENPYERP_API_URL}{endpoint}",
            headers=_api_headers(token),
            params=params or {},
            timeout=10.0,
        )

        # Token süresi dolduysa yenile (API Key kullanılıyorsa bu olmaz)
        if r.status_code == 401 and not OPENPYERP_API_KEY:
            _jwt_token    = None
            _token_suresi = None
            token = await openpyerp_token()
            r = await client.get(
                f"{OPENPYERP_API_URL}{endpoint}",
                headers=_api_headers(token),
                params=params or {},
                timeout=10.0,
            )

        r.raise_for_status()
        return r.json()


# Geriye dönük uyumluluk alias'ları
carimatik_token = openpyerp_token
carimatik_get   = openpyerp_get


# ══════════════════════════════════════════════════════════════
#  MESAJ ANLAMA — hangi soruya hangi API çağrısı?
# ══════════════════════════════════════════════════════════════

INTENT_KURALLARI = [
    # (regex pattern, intent_adi)
    (r"özet|genel durum|bugün|dashboard|rapor",          "ozet"),
    (r"banka|bakiye|hesap",                               "banka_bakiye"),
    (r"kasa",                                             "kasa_bakiye"),
    (r"cari|müşteri|borç|alacak",                        "cari_listesi"),
    (r"fatura|sipariş|açık belge",                        "acik_faturalar"),
    (r"stok|ürün|malzeme|miktar",                         "stok_listesi"),
    (r"çek|senet|vade",                                   "cek_senet"),
    (r"yardım|ne yapabilir|komut|menü",                   "yardim"),
    (r"bugün.*satış|satış.*bugün|günlük satış|bugün ne satt", "bugun_satis"),
    (r"tahsilat|ödeme.*geldi|para.*geldi|tahsil",          "tahsilat_durum"),
    (r"kritik stok|stok.*bitti|az kalan|minimum stok|stok alarm", "kritik_stok"),
]


def intent_bul(metin: str) -> str:
    """Gelen mesaj metninden intent çıkarır."""
    metin_kucuk = metin.lower().strip()
    for pattern, intent in INTENT_KURALLARI:
        if re.search(pattern, metin_kucuk):
            return intent
    return "bilinmiyor"


# ══════════════════════════════════════════════════════════════
#  CARİMATİK VERİSİ → WhatsApp MESAJINA DÖNÜŞTÜR
# ══════════════════════════════════════════════════════════════

async def veri_getir_ve_formatla(intent: str, sirket_id: int, params: dict = None) -> str:
    """
    Intent'e göre CariMatik API'yi çağırır,
    sonucu WhatsApp'ta okunabilir metne çevirir.

    params: NLP katmanından gelen tarih, cari_adi, rapor_adi gibi parametreler.
    """
    params = params or {}
    bugun = date.today()

    # ── Tarih parametrelerini çöz ──────────────────────────────
    # NLP'den gelen tarihler varsa kullan, yoksa bugünü varsay
    _tarih_bas = params.get("tarih_baslangic") or bugun.isoformat()
    _tarih_bit = params.get("tarih_bitis")     or bugun.isoformat()

    # Dönem etiketi — cevap metninde gösterim için
    if _tarih_bas == _tarih_bit == bugun.isoformat():
        _donem_etiket = "bugün"
    elif _tarih_bas == (bugun - timedelta(days=1)).isoformat() and _tarih_bit == _tarih_bas:
        _donem_etiket = "dün"
    else:
        _donem_etiket = f"{_tarih_bas} – {_tarih_bit}"

    # ── Entity parametreleri ───────────────────────────────────
    _cari_adi   = params.get("cari_adi")
    _rapor_adi  = params.get("rapor_adi")
    _limit      = int(params.get("limit", 500))

    try:
        if intent == "ozet":
            # OpenPyERP'de tek /ozet endpoint yok — paralel sorgularla hesaplıyoruz
            import asyncio
            acik_fatura_t, kasa_t = await asyncio.gather(
                openpyerp_get("/api/v2/belgeler/", {
                    "sirket_id": sirket_id, "durum": "ACIK",
                    "belge_tip": "FATURA", "limit": 1
                }),
                openpyerp_get("/api/v2/kasa-hareketleri/v/bakiye", {
                    "sirket_id": sirket_id
                }),
                return_exceptions=True
            )
            acik_fatura = acik_fatura_t.get("toplam_kayit", 0) if isinstance(acik_fatura_t, dict) else 0
            kasa_net    = kasa_t.get("net_bakiye", 0) if isinstance(kasa_t, dict) else 0

            return (
                f"📊 *Genel Durum*\n"
                f"──────────────\n"
                f"Açık fatura: *{acik_fatura}*\n"
                f"Kasa bakiye: *{float(kasa_net):,.2f} ₺*"
            )

        elif intent == "banka_bakiye":
            hesaplar = await openpyerp_get("/api/v2/banka-hesaplari/", {"sirket_id": sirket_id, "aktif": True})
            if not hesaplar:
                return "Tanımlı banka hesabı bulunamadı."
            satirlar = ["🏦 *Banka Hesapları*\n──────────────"]
            for h in hesaplar[:5]:  # Max 5 hesap
                bakiye = await openpyerp_get(f"/api/v2/banka-hesaplari/{h['id']}/bakiye")
                satirlar.append(f"{h['ad']}: *{bakiye.get('bakiye', 0):,.2f} ₺*")
            return "\n".join(satirlar)

        elif intent == "kasa_bakiye":
            kasalar = await openpyerp_get("/api/v2/kasa-hesaplari/", {"sirket_id": sirket_id, "aktif": True})
            if not kasalar:
                return "Tanımlı kasa hesabı bulunamadı."
            satirlar = ["💰 *Kasa Hesapları*\n──────────────"]
            for k in kasalar[:5]:
                bakiye = await openpyerp_get(f"/api/v2/kasa-hesaplari/{k['id']}/bakiye")
                satirlar.append(f"{k['ad']}: *{bakiye.get('bakiye', 0):,.2f} ₺*")
            return "\n".join(satirlar)

        elif intent == "cari_listesi":
            cari_params = {"sirket_id": sirket_id, "aktif": True, "limit": 5}
            if _cari_adi:
                cari_params["q"] = _cari_adi   # OpenPyERP arama parametresi: q
            # Bakiye özetiyle birlikte tek endpoint
            cariler = await openpyerp_get("/api/v2/cariler/v/bakiye-ozet", cari_params)
            if not cariler:
                return "Kayıtlı cari bulunamadı."
            satirlar = ["👥 *Cariler*\n──────────────"]
            for c in (cariler if isinstance(cariler, list) else cariler.get("items", []))[:5]:
                b = float(c.get("bakiye", 0))
                durum = "alacak" if b >= 0 else "borç"
                satirlar.append(f"{c.get('unvan','?')}: *{abs(b):,.2f} ₺* ({durum})")
            return "\n".join(satirlar)

        elif intent == "acik_faturalar":
            belgeler = await openpyerp_get("/api/v2/belgeler/", {
                "sirket_id": sirket_id,
                "belge_tip": "FATURA",
                "durum": "ACIK",
                "limit": 5
            })
            if not belgeler:
                return "Açık fatura bulunamadı."
            satirlar = ["🧾 *Açık Faturalar*\n──────────────"]
            for b in belgeler[:5]:
                satirlar.append(
                    f"{b.get('belge_no','?')} — "
                    f"{b.get('cari_unvan','?')} — "
                    f"*{float(b.get('toplam_kdvli', b.get('genel_toplam', 0))):,.2f} ₺*"
                )
            return "\n".join(satirlar)

        elif intent == "stok_listesi":
            stoklar_resp = await openpyerp_get("/api/v2/stok-kartlari/", {
                "sirket_id": sirket_id, "aktif": True, "limit": 5
            })
            stoklar = stoklar_resp if isinstance(stoklar_resp, list) else stoklar_resp.get("items", [])
            if not stoklar:
                return "Kayıtlı stok bulunamadı."
            # Toplu miktar — tek HTTP çağrısı (N+1 yok)
            stok_idler = [s["id"] for s in stoklar]
            miktarlar_resp = await openpyerp_get("/api/v2/stok-kartlari/v/miktarlar", {
                "sirket_id": sirket_id
            })
            miktar_map = {m["stok_id"]: m["miktar"] for m in miktarlar_resp} if isinstance(miktarlar_resp, list) else {}
            satirlar = ["📦 *Stok Durumu*\n──────────────"]
            for s in stoklar[:5]:
                m = miktar_map.get(s["id"], 0)
                satirlar.append(f"{s['ad']}: *{float(m):,.2f}*")
            return "\n".join(satirlar)

        elif intent == "cek_senet":
            cekler = await openpyerp_get("/api/v2/cek-senetler/", {
                "sirket_id": sirket_id,
                "durum":     "PORTFOY",
                "limit":     5,
            })
            if not cekler:
                return "Portföyde çek/senet bulunamadı."
            satirlar = ["📋 *Portföydeki Çek/Senetler*\n──────────────"]
            for c in cekler[:5]:
                satirlar.append(
                    f"{c.get('tip','?')} — {c.get('vade_tarihi','?')} — "
                    f"*{c.get('tutar', 0):,.2f} ₺*"
                )
            return "\n".join(satirlar)

        elif intent == "rapor_calistir":
            # Rapor adı veya ID ile arama
            if _rapor_adi:
                raporlar = await openpyerp_get("/api/v2/raporlar/", {
                    "sirket_id": sirket_id,
                    "arama":     _rapor_adi,
                    "aktif":     True,
                })
            else:
                raporlar = await openpyerp_get("/api/v2/raporlar/", {
                    "sirket_id": sirket_id,
                    "aktif":     True,
                    "limit":     10,
                })

            if not raporlar:
                return (
                    "Rapor bulunamadı. Rapor adını daha açık yazar mısınız?\n"
                    "Örnek: *nisan satış raporu* veya *stok raporu*"
                )

            if len(raporlar) > 1 and not _rapor_adi:
                satirlar = ["📋 *Mevcut Raporlar*\n──────────────"]
                for r in raporlar[:8]:
                    satirlar.append(f"• {r.get('ad', '?')}")
                satirlar.append("\nHangisini çalıştırmamı istersiniz?")
                return "\n".join(satirlar)

            rapor = raporlar[0]
            rapor_id = rapor["id"]

            # Parametreli çalıştırma
            calistir_params = {
                "sirket_id":       sirket_id,
                "tarih_baslangic": _tarih_bas,
                "tarih_bitis":     _tarih_bit,
            }
            if _cari_adi:
                calistir_params["cari_adi"] = _cari_adi

            sonuc = await openpyerp_get(
                f"/api/v2/raporlar/{rapor_id}/calistir",
                calistir_params
            )

            if not sonuc:
                return f"📋 *{rapor.get('ad')}* raporu boş sonuç döndürdü."

            # İlk 8 satırı formatla
            basliklar = sonuc.get("kolonlar", [])
            satirlar_data = sonuc.get("satirlar", [])[:8]

            if not basliklar or not satirlar_data:
                return f"📋 *{rapor.get('ad')}* — veri bulunamadı."

            cevap_satirlar = [
                f"📋 *{rapor.get('ad')}* ({_donem_etiket})\n──────────────"
            ]
            for satir in satirlar_data:
                satir_metin = " | ".join(str(satir.get(k, ""))[:15] for k in basliklar[:3])
                cevap_satirlar.append(satir_metin)

            if len(sonuc.get("satirlar", [])) > 8:
                cevap_satirlar.append(f"\n_(+{len(sonuc['satirlar'])-8} satır daha)_")

            return "\n".join(cevap_satirlar)

        elif intent == "yardim":
            return (
                "🤖 *OpenPyERP BI — Komutlar*\n"
                "──────────────\n"
                "• *özet* — genel finansal durum\n"
                "• *banka* — banka hesap bakiyeleri\n"
                "• *kasa* — kasa bakiyeleri\n"
                "• *cari* — müşteri/tedarikçi listesi\n"
                "• *fatura* — açık faturalar\n"
                "• *stok* — stok durumu\n"
                "• *çek* — portföydeki çek/senetler\n"
                "• *bugün satış* — bugünkü satış toplamı\n"
                "• *tahsilat* — bugünkü tahsilatlar\n"
                "• *kritik stok* — azalan stoklar"
            )

        elif intent == "bugun_satis":
            belgeler_resp = await openpyerp_get("/api/v2/belgeler/", {
                "sirket_id":       sirket_id,
                "belge_tip":       "FATURA",
                "cari_tip":        "SATIS",
                "tarih_baslangic": _tarih_bas,
                "tarih_bitis":     _tarih_bit,
                "limit":           _limit,
            })
            belgeler = belgeler_resp if isinstance(belgeler_resp, list) else belgeler_resp.get("items", [])
            if not belgeler:
                return f"📅 *Satış* ({_donem_etiket})\n──────────────\nBu dönemde satış faturası bulunamadı."

            toplam = sum(float(b.get("toplam_kdvli", b.get("genel_toplam", 0))) for b in belgeler)
            kdvsiz = sum(float(b.get("toplam_kdvsiz", b.get("ara_toplam",  0))) for b in belgeler)
            adet       = len(belgeler)
            ort        = toplam / adet if adet else 0

            # En yüksek 3 fatura
            sirali = sorted(belgeler, key=lambda b: float(b.get("genel_toplam", 0)), reverse=True)
            en_yuksek = "\n".join(
                f"  {str(b.get('cari_id','?'))[:20]}: *{float(b.get('toplam_kdvli', b.get('genel_toplam',0))):,.2f} ₺*"
                for b in sirali[:3]
            )

            return (
                f"📅 *Satış* ({_donem_etiket})\n"
                f"──────────────\n"
                f"Fatura adedi: *{adet}*\n"
                f"KDV hariç: *{kdvsiz:,.2f} ₺*\n"
                f"KDV dahil: *{toplam:,.2f} ₺*\n"
                f"Ortalama fatura: *{ort:,.2f} ₺*\n\n"
                f"🔝 En yüksek 3:\n{en_yuksek}"
            )

        elif intent == "tahsilat_durum":
            # Banka tahsilatları
            banka_hareketler = await openpyerp_get("/api/v2/banka-hareketleri/", {
                "tarih_baslangic": _tarih_bas,
                "tarih_bitis":     _tarih_bit,
                "limit":           500,
            })
            banka_tahsilat = sum(
                float(h.get("tutar", 0))
                for h in banka_hareketler
                if h.get("hareket_tipi") == "ALACAK"
            )

            # Kasa tahsilatları
            kasa_hareketler = await openpyerp_get("/api/v2/kasa-hareketleri/", {
                "tarih_baslangic": _tarih_bas,
                "tarih_bitis":     _tarih_bit,
                "limit":           500,
            })
            kasa_tahsilat = sum(
                float(h.get("tutar", 0))
                for h in kasa_hareketler
                if h.get("hareket_tipi") == "GIRIS"
            )

            # Cari tahsilatlar (ödeme fişleri)
            cari_tahsilatlar = await openpyerp_get("/api/v2/cari-hareketler/", {
                "hareket_tipi":    "TAHSILAT",
                "tarih_baslangic": _tarih_bas,
                "tarih_bitis":     _tarih_bit,
            })
            cari_toplam = sum(float(h.get("tutar", 0)) for h in cari_tahsilatlar)

            genel_toplam = banka_tahsilat + kasa_tahsilat

            if genel_toplam == 0 and cari_toplam == 0:
                return f"💳 *Tahsilat Durumu* ({_donem_etiket})\n──────────────\nBu dönemde tahsilat girilmemiş."

            return (
                f"💳 *Tahsilat Durumu* ({_donem_etiket})\n"
                f"──────────────\n"
                f"Bankaya gelen: *{banka_tahsilat:,.2f} ₺*\n"
                f"Kasaya gelen: *{kasa_tahsilat:,.2f} ₺*\n"
                f"Cari tahsilat: *{cari_toplam:,.2f} ₺*\n"
                f"──────────────\n"
                f"Toplam: *{genel_toplam:,.2f} ₺*"
            )

        elif intent == "kritik_stok":
            # Tüm aktif malzeme stoklarını çek
            stoklar_resp = await openpyerp_get("/api/v2/stok-kartlari/", {
                "sirket_id": sirket_id,
                "tip":       "MALZEME",
                "aktif":     True,
            })
            stoklar = stoklar_resp if isinstance(stoklar_resp, list) else stoklar_resp.get("items", [])
            if not stoklar:
                return "Kayıtlı stok bulunamadı."

            bugun    = date.today()
            otuz_gun = (bugun - timedelta(days=30)).isoformat()
            kritikler = []

            # Tüm stok miktarlarını tek sorguda al (N+1 yok)
            miktarlar_resp = await openpyerp_get("/api/v2/stok-kartlari/v/miktarlar", {
                "sirket_id": sirket_id
            })
            miktar_map = {m["stok_id"]: float(m.get("miktar", 0))
                          for m in (miktarlar_resp if isinstance(miktarlar_resp, list) else [])}

            # StokKarti'nda min_stok alanı var — önce onu kullan
            for stok in stoklar:
                sid    = stok["id"]
                mevcut = miktar_map.get(sid, 0)
                min_stok = float(stok.get("min_stok") or 0)

                if min_stok > 0:
                    # min_stok tanımlıysa direkt karşılaştır
                    if mevcut > min_stok:
                        continue
                    gun_kaldi = 0  # Eşiğin altında
                    kritikler.append({"ad": stok["ad"], "mevcut": mevcut,
                                      "gun_kaldi": gun_kaldi, "birim": ""})
                    continue

                # min_stok yoksa dinamik hesap: son 30 gün ortalama çıkış × 7
                cikislar_resp = await openpyerp_get("/api/v2/stok-hareketleri/", {
                    "stok_id":         sid,
                    "hareket_tipi":    "CIKIS",
                    "tarih_baslangic": otuz_gun,
                    "tarih_bitis":     bugun.isoformat(),
                })
                cikislar     = cikislar_resp if isinstance(cikislar_resp, list) else cikislar_resp.get("items", [])
                cikis_toplam = sum(float(h.get("miktar", 0)) for h in cikislar)

                # Günlük ortalama çıkış
                gunluk_ort = cikis_toplam / 30

                # Eşik: 7 günlük ihtiyaç (haftalık sipariş döngüsü varsayımı)
                esik = gunluk_ort * 7

                # Hiç hareket yoksa veya stok eşiğin üzerindeyse atla
                if gunluk_ort == 0 or mevcut > esik:
                    continue

                # Kaç güne yeter?
                gun_kaldi = int(mevcut / gunluk_ort) if gunluk_ort > 0 else 0
                kritikler.append({
                    "ad":        stok["ad"],
                    "mevcut":    mevcut,
                    "gun_kaldi": gun_kaldi,
                    "birim":     stok.get("birim_ad", ""),
                })

            if not kritikler:
                return "✅ *Kritik Stok Yok*\nTüm stoklar yeterli seviyede."

            kritikler.sort(key=lambda x: x["gun_kaldi"])
            satirlar = [f"⚠️ *Kritik Stok Uyarısı* ({len(kritikler)} ürün)\n──────────────"]
            for k in kritikler[:8]:
                emoji = "🔴" if k["gun_kaldi"] <= 2 else "🟡"
                satirlar.append(
                    f"{emoji} {k['ad'][:25]}\n"
                    f"   Mevcut: *{k['mevcut']:,.1f} {k['birim']}* "
                    f"— yaklaşık *{k['gun_kaldi']} gün*"
                )
            return "\n".join(satirlar)

        else:
            return (
                "Anlayamadım. *yardım* yazarak komut listesini görebilirsiniz."
            )

    except httpx.HTTPStatusError as e:
        log.error(f"CariMatik API hatasi: {e.response.status_code} {e.response.text}")
        return "Veri alınırken hata oluştu, lütfen tekrar deneyin."
    except Exception as e:
        log.error(f"Beklenmeyen hata: {e}")
        return "Bir hata oluştu, lütfen tekrar deneyin."


# ══════════════════════════════════════════════════════════════
#  META CLOUD API — MESAJ GÖNDER
# ══════════════════════════════════════════════════════════════

async def whatsapp_gonder(wa_no: str, metin: str, ayar: "WaSirketAyar") -> bool:
    """Meta Cloud API üzerinden WhatsApp mesajı gönderir. Her şirket kendi token'ını kullanır."""
    if not ayar or not ayar.wa_token or not ayar.wa_phone_id:
        log.error(f"Sirket Meta ayarlari eksik — mesaj gonderilemedi: {wa_no}")
        return False

    url = f"https://graph.facebook.com/v19.0/{ayar.wa_phone_id}/messages"

    payload = {
        "messaging_product": "whatsapp",
        "to": wa_no,
        "type": "text",
        "text": {"body": metin, "preview_url": False},
    }

    async with httpx.AsyncClient() as client:
        r = await client.post(
            url,
            headers={
                "Authorization": f"Bearer {ayar.wa_token}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=10.0,
        )

    if r.status_code == 200:
        log.info(f"Mesaj gonderildi → {wa_no}")
        return True
    else:
        log.error(f"Mesaj gonderilemedi: {r.status_code} {r.text}")
        return False


# ══════════════════════════════════════════════════════════════
#  MESAJ KAYIT — faturalandırma için
# ══════════════════════════════════════════════════════════════

def mesaj_logla(
    db: Session,
    sirket_id: int,
    wa_no: str,
    yon: str,
    mesaj_ozet: str,
    ucretli: bool = False,
    meta_usd: float = 0.0,
):
    """Her mesajı wa_mesaj_log tablosuna yazar."""
    log_kaydi = WaMesajLog(
        sirket_id  = sirket_id,
        wa_no      = wa_no,
        yon        = yon,
        mesaj_tipi = "utility" if ucretli else "servis",
        mesaj_ozet = mesaj_ozet[:200],
        ucretli    = ucretli,
        meta_usd   = meta_usd,
    )
    db.add(log_kaydi)
    db.commit()


# ══════════════════════════════════════════════════════════════
#  FASTAPI UYGULAMA
# ══════════════════════════════════════════════════════════════

app = FastAPI(
    title="CariMatik WhatsApp BI",
    description="Meta Cloud API webhook — CariMatik API entegrasyonu",
    version="1.0.0",
)


@app.on_event("startup")
async def startup():
    tablolari_olustur()
    log.info("WhatsApp BI servisi baslatildi")


# ── Webhook doğrulama (Meta'nın ilk bağlantı kontrolü) ────────
@app.get("/webhook")
async def webhook_dogrula(
    hub_mode: str       = None,
    hub_challenge: str  = None,
    hub_verify_token: str = None,
):
    """
    Meta, webhook URL'ini ilk kez kaydederken bu endpoint'i çağırır.
    VERIFY_TOKEN eşleşirse challenge'ı geri döndürür → bağlantı onaylanır.
    """
    if hub_mode == "subscribe" and hub_verify_token == VERIFY_TOKEN:
        log.info("Webhook dogrulandi")
        return PlainTextResponse(hub_challenge)
    raise HTTPException(status_code=403, detail="Dogrulama basarisiz")


# ── Gelen mesaj işleme ─────────────────────────────────────────
@app.post("/webhook")
async def webhook_mesaj(request: Request, db: Session = Depends(get_db)):
    """
    Meta'dan gelen her mesaj olayı buraya düşer.
    Mesajı işler, CariMatik'ten veriyi çeker, cevap gönderir.
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Gecersiz JSON")

    # Meta webhook yapısını parse et
    try:
        entry    = body["entry"][0]
        change   = entry["changes"][0]["value"]
        mesajlar = change.get("messages", [])
    except (KeyError, IndexError):
        # Durum güncellemesi veya farklı olay tipi — görmezden gel
        return {"status": "ok"}

    for msg in mesajlar:
        # Sadece metin mesajlarını işle
        if msg.get("type") != "text":
            continue

        wa_no       = msg["from"]                    # +905321234567
        metin       = msg["text"]["body"].strip()
        mesaj_id    = msg.get("id", "")

        log.info(f"Gelen mesaj: {wa_no} → '{metin[:50]}'")

        # Kullanıcıyı DB'de bul
        kullanici = db.query(WaKullanici).filter_by(
            wa_no=wa_no, aktif=True
        ).first()

        if not kullanici:
            # Kayıtsız kullanıcı — kayıtsız mesajları logla, cevap verme
            log.warning(f"Kayitsiz kullanici: {wa_no}")
            continue

        # Şirketin Meta ayarlarını yükle
        ayar = db.query(WaSirketAyar).filter_by(
            sirket_id=kullanici.sirket_id, wa_aktif=True
        ).first()

        if not ayar:
            log.warning(f"Sirket {kullanici.sirket_id} icin Meta ayari yok")
            continue

        # Token yaşını kontrol et — 50 günden eskiyse uyarı logla
        if ayar.token_son_guncelleme:
            gun_fark = (datetime.now() - ayar.token_son_guncelleme).days
            if gun_fark >= 50:
                log.warning(f"Sirket {kullanici.sirket_id} token {gun_fark} gunluk — yenilenmeli!")

        # Gelen mesajı logla (servis penceresi → ücretsiz)
        mesaj_logla(db, kullanici.sirket_id, wa_no, "GELEN", metin)

        # Intent bul → veriyi getir → cevapla
        intent = intent_bul(metin)
        log.info(f"Intent: {intent} | sirket_id: {kullanici.sirket_id}")

        cevap = await veri_getir_ve_formatla(intent, kullanici.sirket_id, {})

        # Cevabı gönder ve logla
        gonderildi = await whatsapp_gonder(wa_no, cevap, ayar)
        if gonderildi:
            mesaj_logla(
                db, kullanici.sirket_id, wa_no, "GIDEN",
                cevap[:200],
                ucretli=False,
                meta_usd=0.0,
            )

    return {"status": "ok"}


# ── Yönetim endpoint'leri ──────────────────────────────────────

@app.post("/kullanici-ekle")
async def kullanici_ekle(
    wa_no: str,
    sirket_id: int,
    db: Session = Depends(get_db),
):
    """
    Yeni müşteri kaydı ekler.
    Admin panelinden veya curl ile çağrılır.
    """
    mevcut = db.query(WaKullanici).filter_by(wa_no=wa_no).first()
    if mevcut:
        raise HTTPException(status_code=409, detail="Bu numara zaten kayıtlı")

    yeni = WaKullanici(wa_no=wa_no, sirket_id=sirket_id)
    db.add(yeni)
    db.commit()
    db.refresh(yeni)
    log.info(f"Yeni kullanici eklendi: {wa_no} → sirket {sirket_id}")
    return {"ok": True, "id": yeni.id, "wa_no": wa_no, "sirket_id": sirket_id}


@app.get("/kullanicilar")
async def kullanici_listesi(db: Session = Depends(get_db)):
    """Kayıtlı tüm WhatsApp kullanıcılarını listeler."""
    return db.query(WaKullanici).filter_by(aktif=True).all()


@app.get("/maliyet-raporu")
async def maliyet_raporu(
    ay: Optional[int] = None,
    yil: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """
    Şirket bazında aylık mesaj maliyeti raporu.
    Faturalandırma için kullanılır.
    """
    yil = yil or datetime.now().year
    ay  = ay  or datetime.now().month

    sonuclar = (
        db.query(
            WaMesajLog.sirket_id,
            func.count(WaMesajLog.id).label("toplam_mesaj"),
            func.sum(WaMesajLog.meta_usd).label("toplam_usd"),
        )
        .filter(
            func.year(WaMesajLog.tarih)  == yil,
            func.month(WaMesajLog.tarih) == ay,
        )
        .group_by(WaMesajLog.sirket_id)
        .all()
    )

    return [
        {
            "sirket_id":    r.sirket_id,
            "toplam_mesaj": r.toplam_mesaj,
            "toplam_usd":   float(r.toplam_usd or 0),
            "toplam_tl":    float(r.toplam_usd or 0) * 33,  # Kur güncellenmeli
        }
        for r in sonuclar
    ]


@app.get("/sirketler")
async def sirket_listesi(db: Session = Depends(get_db)):
    """Tüm şirket Meta ayarlarını listeler — token yaşını hesaplar."""
    ayarlar = db.query(WaSirketAyar).all()
    sonuc = []
    for a in ayarlar:
        gun_kaldi = None
        if a.token_son_guncelleme:
            gecen = (datetime.now() - a.token_son_guncelleme).days
            gun_kaldi = max(0, 60 - gecen)  # Permanent token 60 gün geçerli
        sonuc.append({
            "sirket_id":          a.sirket_id,
            "wa_phone_id":        a.wa_phone_id,
            "wa_business_id":     a.wa_business_id,
            "wa_aktif":           a.wa_aktif,
            "token_gun_kaldi":    gun_kaldi,
            "token_son_guncelleme": a.token_son_guncelleme.isoformat() if a.token_son_guncelleme else None,
        })
    return sonuc


@app.post("/sirket-ayar-kaydet")
async def sirket_ayar_kaydet(
    sirket_id:      int,
    wa_phone_id:    str,
    wa_business_id: str = None,
    wa_token:       str = None,
    db: Session = Depends(get_db),
):
    """Şirket Meta ayarlarını kaydeder veya günceller."""
    mevcut = db.query(WaSirketAyar).filter_by(sirket_id=sirket_id).first()
    if mevcut:
        mevcut.wa_phone_id      = wa_phone_id
        mevcut.wa_business_id   = wa_business_id
        if wa_token:
            mevcut.wa_token             = wa_token
            mevcut.token_son_guncelleme = datetime.now()
        mevcut.wa_aktif = True
    else:
        ayar = WaSirketAyar(
            sirket_id            = sirket_id,
            wa_phone_id          = wa_phone_id,
            wa_business_id       = wa_business_id,
            wa_token             = wa_token,
            wa_aktif             = True,
            token_son_guncelleme = datetime.now() if wa_token else None,
        )
        db.add(ayar)
    db.commit()
    log.info(f"Sirket {sirket_id} Meta ayarlari kaydedildi")
    return {"ok": True, "sirket_id": sirket_id}


@app.post("/sirket-token-yenile")
async def sirket_token_yenile(
    sirket_id: int,
    wa_token:  str,
    db: Session = Depends(get_db),
):
    """Şirketin token'ını günceller, yenileme tarihini sıfırlar."""
    ayar = db.query(WaSirketAyar).filter_by(sirket_id=sirket_id).first()
    if not ayar:
        raise HTTPException(status_code=404, detail="Şirket ayarı bulunamadı")
    ayar.wa_token             = wa_token
    ayar.token_son_guncelleme = datetime.now()
    db.commit()
    log.info(f"Sirket {sirket_id} token yenilendi")
    return {"ok": True}


@app.post("/kullanici-sil")
async def kullanici_sil(wa_no: str, db: Session = Depends(get_db)):
    """Kullanıcıyı pasife çeker (silmez, log korunur)."""
    kullanici = db.query(WaKullanici).filter_by(wa_no=wa_no).first()
    if not kullanici:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı")
    kullanici.aktif = False
    db.commit()
    return {"ok": True}


@app.get("/mesaj-listesi")
async def mesaj_listesi(
    sirket_id: Optional[int] = None,
    limit:     int           = 50,
    db: Session = Depends(get_db),
):
    """Son mesajları listeler, opsiyonel şirket filtresi."""
    q = db.query(WaMesajLog)
    if sirket_id:
        q = q.filter(WaMesajLog.sirket_id == sirket_id)
    mesajlar = q.order_by(WaMesajLog.tarih.desc()).limit(limit).all()
    return [
        {
            "sirket_id":  m.sirket_id,
            "wa_no":      m.wa_no,
            "yon":        m.yon,
            "mesaj_ozet": m.mesaj_ozet,
            "ucretli":    m.ucretli,
            "meta_usd":   float(m.meta_usd or 0),
            "tarih":      m.tarih.isoformat() if m.tarih else None,
        }
        for m in mesajlar
    ]


@app.get("/health")


async def health():
    return {
        "status": "ok",
        "servis": "WhatsApp BI",
        "zaman": datetime.now().isoformat(),
    }


# ══════════════════════════════════════════════════════════════
#  NLP ENTEGRASYONu — async mesaj işleme
# ══════════════════════════════════════════════════════════════

async def mesaj_isle_async(
    wa_no: str,
    metin: str,
    kullanici,
    ayar,
    db: Session,
):
    """
    Arka planda çalışır — webhook hemen 200 döner.
    Akış:
      1. Anında "⏳ bakıyorum..." gönder
      2. NLP ile intent çöz
      3. Negatif sinyal kontrolü (önceki deneyimi güncelle)
      4. API'yi çağır → cevap gönder
      5. Doğrulama sinyalini kaydet
    """
    from wa_nlp import NLPKatmani

    sirket_id = kullanici.sirket_id
    nlp = NLPKatmani(db, sirket_id)

    # ── Negatif sinyal kontrolü ───────────────────────────────
    # Kullanıcı önceki cevaba itiraz mı ediyor?
    if NLPKatmani.negatif_sinyal_mi(metin):
        son_llm_mesaj = (
            db.query(WaMesajLog)
            .filter_by(sirket_id=sirket_id, wa_no=wa_no, yon="GIDEN")
            .order_by(WaMesajLog.tarih.desc())
            .first()
        )
        if son_llm_mesaj and hasattr(son_llm_mesaj, "deneyim_id") and son_llm_mesaj.deneyim_id:
            nlp.dogrulama_sinyali(son_llm_mesaj.deneyim_id, "negatif")
            await whatsapp_gonder(wa_no,
                "Anlıyorum, yanlış anlamışım. Tekrar yazar mısınız?", ayar)
            return

    # ── Gelen mesajı logla ────────────────────────────────────
    mesaj_logla(db, sirket_id, wa_no, "GELEN", metin)

    # ── NLP çöz ───────────────────────────────────────────────
    sonuc = await nlp.coz(metin)

    # LLM çağrısı gerekiyorsa önce "bakıyorum..." gönder
    if sonuc.kaynak == "llm" or sonuc.sure_ms > 500:
        await whatsapp_gonder(wa_no, "⏳ Bakıyorum...", ayar)

    # ── Bilinmiyorsa fallback mesaj ───────────────────────────
    if sonuc.intent == "bilinmiyor":
        cevap = (
            "Tam anlayamadım. Şunları deneyebilirsiniz:\n"
            "• *yardım* — komut listesi\n"
            "• *özet* — genel durum\n"
            "• *bugün satış* — günlük satış\n\n"
            "Ya da daha açık yazabilir misiniz?"
        )
        await whatsapp_gonder(wa_no, cevap, ayar)
        mesaj_logla(db, sirket_id, wa_no, "GIDEN", cevap[:200])
        return

    # ── API çağır → cevap gönder ──────────────────────────────
    cevap = await veri_getir_ve_formatla(
        sonuc.intent, sirket_id, sonuc.params
    )

    gonderildi = await whatsapp_gonder(wa_no, cevap, ayar)

    if gonderildi:
        mesaj_logla(db, sirket_id, wa_no, "GIDEN", cevap[:200])

        # LLM sonucuna pozitif sinyal — kullanıcı cevabı aldı
        if sonuc.kaynak == "llm" and sonuc.deneyim_id:
            nlp.dogrulama_sinyali(sonuc.deneyim_id, "pozitif")

    log.info(f"Tamamlandı: {wa_no} → {sonuc.intent} "
             f"[{sonuc.kaynak}] {sonuc.sure_ms}ms")
