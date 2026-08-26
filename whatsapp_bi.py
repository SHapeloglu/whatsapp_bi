"""
WhatsApp BI v2.0 — Odoo 18
"""
import os
import hmac
import hashlib
import json
import logging
from datetime import datetime, date, timedelta
from typing import Optional

from fastapi import FastAPI, Request, HTTPException, Depends, BackgroundTasks
from fastapi.responses import PlainTextResponse
import httpx
from sqlalchemy import (
    create_engine, Column, Integer, String,
    Boolean, DateTime, Numeric, Enum, Text,
    ForeignKey, func, extract
)
from sqlalchemy.orm import declarative_base, Session, sessionmaker
from odoo_client import OdooClient

VERIFY_TOKEN = os.getenv("WA_VERIFY_TOKEN", "openpyerp_verify_2026")
APP_SECRET   = os.getenv("WA_APP_SECRET", "")
DATABASE_URI = os.getenv("DATABASE_URL",
    "postgresql+psycopg2://openpyerp_user:sifre@localhost/openpyerp")

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("wa_bi")

odoo = OdooClient()

engine       = create_engine(DATABASE_URI, pool_pre_ping=True, pool_recycle=3600)
SessionLocal = sessionmaker(bind=engine)
Base         = declarative_base()

class WaSirketAyar(Base):
    __tablename__ = "wa_sirket_ayar"
    id                   = Column(Integer, primary_key=True, autoincrement=True)
    sirket_id            = Column(Integer, nullable=False, unique=True)
    odoo_sirket_id       = Column(Integer, nullable=False, default=1)
    wa_phone_id          = Column(String(50))
    wa_business_id       = Column(String(50))
    wa_token             = Column(Text)
    wa_aktif             = Column(Boolean, default=False)
    token_son_guncelleme = Column(DateTime)
    olusturma            = Column(DateTime, default=datetime.now)
    guncelleme           = Column(DateTime, onupdate=datetime.now)

class WaKullanici(Base):
    __tablename__ = "wa_kullanici"
    id        = Column(Integer, primary_key=True, autoincrement=True)
    wa_no     = Column(String(20), nullable=False, unique=True)
    sirket_id = Column(Integer, nullable=False)
    aktif     = Column(Boolean, default=True)
    olusturma = Column(DateTime, default=datetime.now)

class WaMesajLog(Base):
    __tablename__ = "wa_mesaj_log"
    id          = Column(Integer, primary_key=True, autoincrement=True)
    sirket_id   = Column(Integer, nullable=False)
    wa_no       = Column(String(20))
    yon         = Column(Enum("GELEN","GIDEN", name="wa_mesaj_yon"), nullable=False)
    mesaj_tipi  = Column(Enum("servis","utility","marketing", name="wa_mesaj_tipi"), default="servis")
    mesaj_ozet  = Column(String(200))
    ucretli     = Column(Boolean, default=False)
    meta_usd    = Column(Numeric(10,6), default=0)
    deneyim_id  = Column(Integer, nullable=True)
    tarih       = Column(DateTime, default=datetime.now)

class WaIslenmisMesaj(Base):
    __tablename__ = "wa_islenmis_mesaj"
    id         = Column(Integer, primary_key=True, autoincrement=True)
    wa_msg_id  = Column(String(100), unique=True, nullable=False)
    tarih      = Column(DateTime, default=datetime.now)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def tablolari_olustur():
    WaSirketAyar.__table__.create(bind=engine, checkfirst=True)
    WaKullanici.__table__.create(bind=engine, checkfirst=True)
    WaMesajLog.__table__.create(bind=engine, checkfirst=True)
    try:
        from wa_nlp import nlp_tablolari_olustur
        nlp_tablolari_olustur(engine)
    except Exception as e:
        log.warning(f"NLP tabloları oluşturulamadı: {e}")
    log.info("Tüm wa_ tabloları hazır")

async def whatsapp_gonder(wa_no, metin, ayar):
    if not ayar or not ayar.wa_token or not ayar.wa_phone_id:
        log.error(f"Meta ayarı eksik: {wa_no}")
        return False
    url = f"https://graph.facebook.com/v19.0/{ayar.wa_phone_id}/messages"
    async with httpx.AsyncClient() as client:
        r = await client.post(url,
            headers={"Authorization": f"Bearer {ayar.wa_token}",
                     "Content-Type": "application/json"},
            json={"messaging_product": "whatsapp", "to": wa_no,
                  "type": "text", "text": {"body": metin, "preview_url": False}},
            timeout=10.0)
    if r.status_code == 200:
        log.info(f"Gönderildi → {wa_no}")
        return True
    log.error(f"Gönderilemedi: {r.status_code} {r.text}")
    return False

def mesaj_logla(db, sirket_id, wa_no, yon, mesaj_ozet,
                ucretli=False, meta_usd=0.0, deneyim_id=None):
    db.add(WaMesajLog(
        sirket_id=sirket_id, wa_no=wa_no, yon=yon,
        mesaj_tipi="utility" if ucretli else "servis",
        mesaj_ozet=mesaj_ozet[:200], ucretli=ucretli,
        meta_usd=meta_usd, deneyim_id=deneyim_id))
    db.commit()

async def veri_getir_ve_formatla(intent, odoo_sirket_id, params=None):
    params    = params or {}
    bugun     = date.today()
    tarih_bas = params.get("tarih_baslangic") or bugun.isoformat()
    tarih_bit = params.get("tarih_bitis")     or bugun.isoformat()
    cari_adi  = params.get("cari_adi")

    if tarih_bas == tarih_bit == bugun.isoformat():
        donem = "bugün"
    elif tarih_bas == (bugun - timedelta(days=1)).isoformat() and tarih_bit == tarih_bas:
        donem = "dün"
    else:
        donem = f"{tarih_bas} – {tarih_bit}"

    try:
        if intent == "ozet":
            v = await odoo.ozet(odoo_sirket_id)
            return (f"📊 *Genel Durum*\n──────────────\n"
                    f"Açık fatura: *{v['acik_fatura_adet']}* adet "
                    f"(*{v['acik_fatura_toplam']:,.2f} ₺* kalan)\n"
                    f"Banka: *{v['banka_bakiye']:,.2f} ₺*\n"
                    f"Kasa: *{v['kasa_bakiye']:,.2f} ₺*")

        elif intent == "banka_bakiye":
            hesaplar = await odoo.banka_bakiye(odoo_sirket_id)
            if not hesaplar:
                return "Tanımlı banka hesabı bulunamadı."
            satirlar = ["🏦 *Banka Hesapları*\n──────────────"]
            for h in hesaplar:
                satirlar.append(f"{h['ad']}: *{h['bakiye']:,.2f} ₺*")
            return "\n".join(satirlar)

        elif intent == "kasa_bakiye":
            kasalar = await odoo.kasa_bakiye(odoo_sirket_id)
            if not kasalar:
                return "Tanımlı kasa bulunamadı."
            satirlar = ["💰 *Kasa Hesapları*\n──────────────"]
            for k in kasalar:
                satirlar.append(f"{k['ad']}: *{k['bakiye']:,.2f} ₺*")
            return "\n".join(satirlar)

        elif intent == "cari_listesi":
            cariler = await odoo.cari_listesi(odoo_sirket_id, arama=cari_adi)
            if not cariler:
                return "Kayıtlı cari bulunamadı."
            satirlar = ["👥 *Cariler*\n──────────────"]
            for c in cariler:
                b = c["bakiye"]
                satirlar.append(f"{c['ad'][:25]} ({c['tip']}): "
                                f"*{abs(b):,.2f} ₺* {'alacak' if b>=0 else 'borç'}")
            return "\n".join(satirlar)

        elif intent == "acik_faturalar":
            faturalar = await odoo.acik_faturalar(odoo_sirket_id)
            if not faturalar:
                return "Açık fatura bulunamadı. 🎉"
            satirlar = ["🧾 *Açık Faturalar*\n──────────────"]
            for f in faturalar:
                satirlar.append(f"{f['numara']} — {f['cari'][:20]}\n"
                                f"   Kalan: *{f['kalan']:,.2f} ₺* | Vade: {f['vade']}")
            return "\n".join(satirlar)

        elif intent == "bugun_satis":
            v = await odoo.satis(odoo_sirket_id, tarih_bas, tarih_bit)
            if v["adet"] == 0:
                return f"📅 *Satış* ({donem})\n──────────────\nFatura bulunamadı."
            en_yuksek = "\n".join(
                f"  {e['cari'][:22]}: *{e['toplam']:,.2f} ₺*" for e in v["en_yuksek"])
            return (f"📅 *Satış* ({donem})\n──────────────\n"
                    f"Fatura: *{v['adet']}* adet\n"
                    f"KDV hariç: *{v['kdvsiz']:,.2f} ₺*\n"
                    f"KDV dahil: *{v['kdvli']:,.2f} ₺*\n"
                    f"Ortalama: *{v['ortalama']:,.2f} ₺*\n\n"
                    f"🔝 En yüksek 3:\n{en_yuksek}")

        elif intent == "tahsilat_durum":
            v = await odoo.tahsilat(odoo_sirket_id, tarih_bas, tarih_bit)
            if v["adet"] == 0:
                return f"💳 *Tahsilat* ({donem})\n──────────────\nTahsilat girilmemiş."
            detay = "\n".join(
                f"  {d['cari'][:22]} → *{d['tutar']:,.2f} ₺* ({d['hesap']})"
                for d in v["detay"])
            return (f"💳 *Tahsilat* ({donem})\n──────────────\n"
                    f"Toplam: *{v['toplam']:,.2f} ₺* ({v['adet']} adet)\n\n"
                    f"Son tahsilatlar:\n{detay}")

        elif intent == "stok_listesi":
            stoklar = await odoo.stok_listesi(odoo_sirket_id)
            if not stoklar:
                return "Stok kaydı bulunamadı."
            satirlar = ["📦 *Stok Durumu*\n──────────────"]
            for s in stoklar:
                satirlar.append(f"{s['urun'][:25]}: *{s['net']:,.2f}* mevcut")
            return "\n".join(satirlar)

        elif intent == "kritik_stok":
            kritikler = await odoo.kritik_stok(odoo_sirket_id)
            if not kritikler:
                return "✅ *Kritik Stok Yok*\nTüm stoklar yeterli seviyede."
            satirlar = [f"⚠️ *Kritik Stok* ({len(kritikler)} ürün)\n──────────────"]
            for k in kritikler[:8]:
                emoji = "🔴" if k["mevcut"] <= 0 else "🟡"
                satirlar.append(f"{emoji} {k['urun'][:25]}\n"
                                f"   Mevcut: *{k['mevcut']:,.1f}* | Min: {k['minimum']:,.1f}")
            return "\n".join(satirlar)

        elif intent == "cek_senet":
            cekler = await odoo.cek_senet(odoo_sirket_id)
            if not cekler:
                return "Bekleyen çek/senet bulunamadı."
            satirlar = ["📋 *Çek / Senet*\n──────────────"]
            for c in cekler:
                satirlar.append(f"{c['cari'][:22]} — {c['tarih']} — "
                                f"*{c['tutar']:,.2f} ₺* ({c['tip']})")
            return "\n".join(satirlar)

        elif intent == "yardim":
            return ("🤖 *WhatsApp BI — Komutlar*\n──────────────\n"
                    "• *özet* — genel finansal durum\n"
                    "• *banka* — banka hesap bakiyeleri\n"
                    "• *kasa* — kasa bakiyeleri\n"
                    "• *cari* — müşteri/tedarikçi listesi\n"
                    "• *fatura* — açık faturalar\n"
                    "• *stok* — stok durumu\n"
                    "• *kritik stok* — azalan stoklar\n"
                    "• *çek* — bekleyen çek/senetler\n"
                    "• *bugün satış* — günlük satış\n"
                    "• *tahsilat* — tahsilat durumu\n\n"
                    "Tarih filtreleyebilirsiniz:\n"
                    "_dünkü satış, bu hafta tahsilat_")

        else:
            return "Anlayamadım. *yardım* yazarak komut listesini görebilirsiniz."

    except Exception as e:
        log.error(f"Odoo sorgu hatası [{intent}]: {e}", exc_info=True)
        return "Veri alınırken hata oluştu, lütfen tekrar deneyin."

app = FastAPI(title="WhatsApp BI — Odoo 18", version="2.0.0")

@app.on_event("startup")
async def startup():
    tablolari_olustur()
    ping = await odoo.ping()
    if ping["durum"] == "ok":
        log.info(f"Odoo bağlantısı OK — v{ping['odoo_versiyonu']} uid={ping['uid']}")
    else:
        log.error(f"Odoo bağlantısı BAŞARISIZ: {ping['mesaj']}")


def imza_dogrula(raw_body: bytes, header: str, secret: str) -> bool:
    if not secret:
        return True  # Secret tanımlı değilse geç (geliştirme modu)
    beklenen = "sha256=" + hmac.new(
        secret.encode(), raw_body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(beklenen, header)

@app.get("/webhook")
async def webhook_dogrula(hub_mode=None, hub_challenge=None, hub_verify_token=None):
    if hub_mode == "subscribe" and hub_verify_token == VERIFY_TOKEN:
        return PlainTextResponse(hub_challenge)
    raise HTTPException(status_code=403, detail="Doğrulama başarısız")

@app.post("/webhook")
async def webhook_mesaj(request: Request, background_tasks: BackgroundTasks,
                        db: Session = Depends(get_db)):
    raw_body = await request.body()
    imza     = request.headers.get("X-Hub-Signature-256", "")
    if not imza_dogrula(raw_body, imza, APP_SECRET):
        log.warning("HMAC imza doğrulaması başarısız — sahte istek!")
        raise HTTPException(status_code=403, detail="İmza geçersiz")
    try:
        body = json.loads(raw_body)
    except Exception:
        raise HTTPException(status_code=400, detail="Geçersiz JSON")
    try:
        entry    = body["entry"][0]
        change   = entry["changes"][0]["value"]
        mesajlar = change.get("messages", [])
    except (KeyError, IndexError):
        return {"status": "ok"}

    for msg in mesajlar:
        wa_msg_id = msg.get("id", "")
        if wa_msg_id:
            zaten_var = db.query(WaIslenmisMesaj).filter_by(wa_msg_id=wa_msg_id).first()
            if zaten_var:
                log.warning(f"Duplicate mesaj atlandı: {wa_msg_id}")
                continue
            db.add(WaIslenmisMesaj(wa_msg_id=wa_msg_id))
            db.commit()
        wa_no = msg["from"]
        kullanici = db.query(WaKullanici).filter_by(wa_no=wa_no, aktif=True).first()
        if not kullanici:
            log.warning(f"Kayıtsız kullanıcı: {wa_no}")
            continue
        ayar = db.query(WaSirketAyar).filter_by(
            sirket_id=kullanici.sirket_id, wa_aktif=True).first()
        if not ayar:
            log.warning(f"Şirket {kullanici.sirket_id} Meta ayarı yok")
            continue
        if msg.get("type") != "text":
            log.info(f"Medya mesajı reddedildi: {wa_no} (tip: {msg.get('type')})")
            background_tasks.add_task(
                whatsapp_gonder, wa_no,
                "Şu an sadece metin mesajlarını anlıyorum. "
                "Sorgunuzu yazı olarak gönderebilir misiniz?", ayar)
            continue
        metin = msg["text"]["body"].strip()
        log.info(f"Gelen: {wa_no} → '{metin[:50]}'")
        if ayar.token_son_guncelleme:
            gun_fark = (datetime.now() - ayar.token_son_guncelleme).days
            if gun_fark >= 50:
                log.warning(f"Token {gun_fark} günlük — yenilenmeli!")
        background_tasks.add_task(mesaj_isle_async, wa_no, metin, kullanici, ayar, db)
    return {"status": "ok"}

async def mesaj_isle_async(wa_no, metin, kullanici, ayar, db):
    from wa_nlp import NLPKatmani
    sirket_id      = kullanici.sirket_id
    odoo_sirket_id = ayar.odoo_sirket_id
    nlp = NLPKatmani(db, sirket_id)

    if NLPKatmani.negatif_sinyal_mi(metin):
        son_giden = (db.query(WaMesajLog)
            .filter_by(sirket_id=sirket_id, wa_no=wa_no, yon="GIDEN")
            .order_by(WaMesajLog.tarih.desc()).first())
        if son_giden and son_giden.deneyim_id:
            nlp.dogrulama_sinyali(son_giden.deneyim_id, "negatif")
            await whatsapp_gonder(wa_no,
                "Anlıyorum, yanlış anlamışım. Tekrar yazar mısınız?", ayar)
            return

    mesaj_logla(db, sirket_id, wa_no, "GELEN", metin)
    sonuc = await nlp.coz(metin)

    if sonuc.kaynak == "llm" or sonuc.sure_ms > 500:
        await whatsapp_gonder(wa_no, "⏳ Bakıyorum...", ayar)

    if sonuc.intent == "bilinmiyor":
        cevap = ("Tam anlayamadım. Şunları deneyebilirsiniz:\n"
                 "• *yardım* — komut listesi\n"
                 "• *özet* — genel durum\n"
                 "• *bugün satış* — günlük satış")
        await whatsapp_gonder(wa_no, cevap, ayar)
        mesaj_logla(db, sirket_id, wa_no, "GIDEN", cevap[:200])
        return

    cevap = await veri_getir_ve_formatla(sonuc.intent, odoo_sirket_id, sonuc.params)
    gonderildi = await whatsapp_gonder(wa_no, cevap, ayar)
    if gonderildi:
        mesaj_logla(db, sirket_id, wa_no, "GIDEN", cevap[:200],
                    deneyim_id=sonuc.deneyim_id)
        if sonuc.kaynak == "llm" and sonuc.deneyim_id:
            nlp.dogrulama_sinyali(sonuc.deneyim_id, "pozitif")
    log.info(f"Tamamlandı: {wa_no} → {sonuc.intent} [{sonuc.kaynak}] {sonuc.sure_ms}ms")

@app.get("/saglik")
async def saglik():
    ping = await odoo.ping()
    return {"whatsapp_bi": "ok", "odoo": ping}

@app.post("/kullanici-ekle")
async def kullanici_ekle(wa_no: str, sirket_id: int, db: Session = Depends(get_db)):
    if db.query(WaKullanici).filter_by(wa_no=wa_no).first():
        raise HTTPException(status_code=409, detail="Numara zaten kayıtlı")
    yeni = WaKullanici(wa_no=wa_no, sirket_id=sirket_id)
    db.add(yeni)
    db.commit()
    db.refresh(yeni)
    return {"ok": True, "id": yeni.id, "wa_no": wa_no, "sirket_id": sirket_id}

@app.post("/sirket-ayar-kaydet")
async def sirket_ayar_kaydet(sirket_id: int, odoo_sirket_id: int,
                              wa_phone_id: str, wa_business_id: str = None,
                              wa_token: str = None, db: Session = Depends(get_db)):
    mevcut = db.query(WaSirketAyar).filter_by(sirket_id=sirket_id).first()
    if mevcut:
        mevcut.odoo_sirket_id = odoo_sirket_id
        mevcut.wa_phone_id    = wa_phone_id
        mevcut.wa_business_id = wa_business_id
        if wa_token:
            mevcut.wa_token             = wa_token
            mevcut.token_son_guncelleme = datetime.now()
        mevcut.wa_aktif = True
    else:
        db.add(WaSirketAyar(
            sirket_id=sirket_id, odoo_sirket_id=odoo_sirket_id,
            wa_phone_id=wa_phone_id, wa_business_id=wa_business_id,
            wa_token=wa_token, wa_aktif=True,
            token_son_guncelleme=datetime.now() if wa_token else None))
    db.commit()
    return {"ok": True}

@app.post("/sirket-token-yenile")
async def sirket_token_yenile(sirket_id: int, wa_token: str,
                               db: Session = Depends(get_db)):
    ayar = db.query(WaSirketAyar).filter_by(sirket_id=sirket_id).first()
    if not ayar:
        raise HTTPException(status_code=404, detail="Ayar bulunamadı")
    ayar.wa_token             = wa_token
    ayar.token_son_guncelleme = datetime.now()
    db.commit()
    return {"ok": True}

@app.get("/odoo-sirketler")
async def odoo_sirketler():
    return await odoo.sirket_listesi()

@app.get("/kullanicilar")
async def kullanici_listesi(db: Session = Depends(get_db)):
    return db.query(WaKullanici).filter_by(aktif=True).all()

@app.post("/kullanici-sil")
async def kullanici_sil(wa_no: str, db: Session = Depends(get_db)):
    k = db.query(WaKullanici).filter_by(wa_no=wa_no).first()
    if not k:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı")
    k.aktif = False
    db.commit()
    return {"ok": True}

@app.get("/mesaj-listesi")
async def mesaj_listesi(sirket_id: Optional[int] = None, limit: int = 50,
                        db: Session = Depends(get_db)):
    q = db.query(WaMesajLog)
    if sirket_id:
        q = q.filter(WaMesajLog.sirket_id == sirket_id)
    mesajlar = q.order_by(WaMesajLog.tarih.desc()).limit(limit).all()
    return [{"sirket_id": m.sirket_id, "wa_no": m.wa_no, "yon": m.yon,
             "mesaj_ozet": m.mesaj_ozet,
             "tarih": m.tarih.isoformat() if m.tarih else None}
            for m in mesajlar]

@app.get("/maliyet-raporu")
async def maliyet_raporu(ay: Optional[int] = None, yil: Optional[int] = None,
                         db: Session = Depends(get_db)):
    yil = yil or datetime.now().year
    ay  = ay  or datetime.now().month
    sonuclar = (db.query(WaMesajLog.sirket_id,
                func.count(WaMesajLog.id).label("toplam_mesaj"),
                func.sum(WaMesajLog.meta_usd).label("toplam_usd"))
        .filter(extract("year",  WaMesajLog.tarih) == yil,
                extract("month", WaMesajLog.tarih) == ay)
        .group_by(WaMesajLog.sirket_id).all())
    return [{"sirket_id": r.sirket_id, "toplam_mesaj": r.toplam_mesaj,
             "toplam_usd": float(r.toplam_usd or 0)} for r in sonuclar]
