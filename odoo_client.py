"""
odoo_client.py — Odoo 18 XML-RPC İstemcisi
"""
import os
import asyncio
import logging
import xmlrpc.client
from datetime import date, timedelta
from typing import Optional

log = logging.getLogger("odoo_client")

ODOO_URL      = os.getenv("ODOO_URL",      "http://localhost:8078")
ODOO_DB       = os.getenv("ODOO_DB",       "isg")
ODOO_USER     = os.getenv("ODOO_USER",     "admin")
ODOO_PASSWORD = os.getenv("ODOO_PASSWORD", "")

def _xmlrpc_common():
    return xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common")

def _xmlrpc_models():
    return xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object")

def _authenticate() -> int:
    uid = _xmlrpc_common().authenticate(ODOO_DB, ODOO_USER, ODOO_PASSWORD, {})
    if not uid:
        raise ConnectionError(f"Odoo kimlik doğrulama başarısız. DB={ODOO_DB!r}, user={ODOO_USER!r}")
    return uid

def _search_read(uid, model, domain, fields, limit=80, offset=0, order=""):
    kwargs = {"fields": fields, "limit": limit, "offset": offset}
    if order:
        kwargs["order"] = order
    return _xmlrpc_models().execute_kw(
        ODOO_DB, uid, ODOO_PASSWORD, model, "search_read", [domain], kwargs
    )

class OdooClient:
    def __init__(self):
        self._uid = None

    async def _get_uid(self):
        if not self._uid:
            self._uid = await asyncio.to_thread(_authenticate)
        return self._uid

    async def _sr(self, model, domain, fields, limit=80, order=""):
        uid = await self._get_uid()
        return await asyncio.to_thread(_search_read, uid, model, domain, fields, limit, 0, order)

    async def ping(self):
        try:
            uid = await self._get_uid()
            versiyon = await asyncio.to_thread(lambda: _xmlrpc_common().version())
            return {"durum": "ok", "odoo_versiyonu": versiyon.get("server_version", "?"), "uid": uid}
        except Exception as e:
            return {"durum": "hata", "mesaj": str(e)}

    async def _journal_bakiye(self, journal_ids, sirket_id):
        if not journal_ids:
            return 0.0
        uid = await self._get_uid()
        satirlar = await asyncio.to_thread(
            _search_read, uid, "account.move.line",
            [("company_id","=",sirket_id),("journal_id","in",journal_ids),("parent_state","=","posted")],
            ["debit","credit"], 10000
        )
        return sum(float(s["debit"]) - float(s["credit"]) for s in satirlar)

    async def ozet(self, sirket_id):
        acik_f, banka, kasa = await asyncio.gather(
            self._sr("account.move",
                [("company_id","=",sirket_id),("move_type","in",["out_invoice","in_invoice"]),
                 ("payment_state","in",["not_paid","partial"]),("state","=","posted")],
                ["name","amount_residual","currency_id"], 500),
            self._sr("account.journal",
                [("company_id","=",sirket_id),("type","=","bank")], ["name","id"]),
            self._sr("account.journal",
                [("company_id","=",sirket_id),("type","=","cash")], ["name","id"]),
        )
        banka_bakiye = await self._journal_bakiye([j["id"] for j in banka], sirket_id)
        kasa_bakiye  = await self._journal_bakiye([j["id"] for j in kasa],  sirket_id)
        return {
            "acik_fatura_adet":   len(acik_f),
            "acik_fatura_toplam": sum(float(f.get("amount_residual",0)) for f in acik_f),
            "banka_bakiye":       banka_bakiye,
            "kasa_bakiye":        kasa_bakiye,
        }

    async def banka_bakiye(self, sirket_id):
        hesaplar = await self._sr("account.journal",
            [("company_id","=",sirket_id),("type","=","bank")], ["name","id"])
        sonuc = []
        for h in hesaplar:
            bakiye = await self._journal_bakiye([h["id"]], sirket_id)
            sonuc.append({"ad": h["name"], "bakiye": bakiye})
        return sonuc

    async def kasa_bakiye(self, sirket_id):
        kasalar = await self._sr("account.journal",
            [("company_id","=",sirket_id),("type","=","cash")], ["name","id"])
        sonuc = []
        for k in kasalar:
            bakiye = await self._journal_bakiye([k["id"]], sirket_id)
            sonuc.append({"ad": k["name"], "bakiye": bakiye})
        return sonuc

    async def cari_listesi(self, sirket_id, arama=None, limit=8):
        domain = [("company_id","=",sirket_id),("active","=",True),
                  "|",("customer_rank",">",0),("supplier_rank",">",0)]
        if arama:
            domain += ["|",("name","ilike",arama),("vat","ilike",arama)]
        cariler = await self._sr("res.partner", domain,
            ["name","customer_rank","supplier_rank","credit","debit"], limit)
        return [{"ad": c["name"],
                 "tip": "müşteri" if c["customer_rank"] > 0 else "tedarikçi",
                 "bakiye": float(c.get("credit",0)) - float(c.get("debit",0))}
                for c in cariler]

    async def acik_faturalar(self, sirket_id, move_type="out_invoice", limit=8):
        faturalar = await self._sr("account.move",
            [("company_id","=",sirket_id),("move_type","=",move_type),
             ("payment_state","in",["not_paid","partial"]),("state","=","posted")],
            ["name","partner_id","amount_total","amount_residual","invoice_date_due"],
            limit, "invoice_date_due asc")
        return [{"numara": f["name"],
                 "cari":   f["partner_id"][1] if f["partner_id"] else "?",
                 "toplam": float(f["amount_total"]),
                 "kalan":  float(f["amount_residual"]),
                 "vade":   f.get("invoice_date_due") or "Yok"}
                for f in faturalar]

    async def satis(self, sirket_id, tarih_bas, tarih_bit, limit=500):
        faturalar = await self._sr("account.move",
            [("company_id","=",sirket_id),("move_type","=","out_invoice"),
             ("state","=","posted"),("invoice_date",">=",tarih_bas),("invoice_date","<=",tarih_bit)],
            ["name","partner_id","amount_untaxed","amount_total"], limit)
        if not faturalar:
            return {"adet": 0, "kdvsiz": 0.0, "kdvli": 0.0, "ortalama": 0.0, "en_yuksek": []}
        kdvli  = sum(float(f["amount_total"]) for f in faturalar)
        sirali = sorted(faturalar, key=lambda f: float(f["amount_total"]), reverse=True)
        return {
            "adet":      len(faturalar),
            "kdvsiz":    sum(float(f["amount_untaxed"]) for f in faturalar),
            "kdvli":     kdvli,
            "ortalama":  kdvli / len(faturalar),
            "en_yuksek": [{"cari": f["partner_id"][1] if f["partner_id"] else "?",
                           "toplam": float(f["amount_total"])} for f in sirali[:3]],
        }

    async def tahsilat(self, sirket_id, tarih_bas, tarih_bit):
        odemeler = await self._sr("account.payment",
            [("company_id","=",sirket_id),("payment_type","=","inbound"),
             ("state","=","posted"),("date",">=",tarih_bas),("date","<=",tarih_bit)],
            ["partner_id","amount","journal_id","date"], 500)
        if not odemeler:
            return {"toplam": 0.0, "adet": 0, "detay": []}
        return {
            "toplam": sum(float(o["amount"]) for o in odemeler),
            "adet":   len(odemeler),
            "detay":  [{"cari":  o["partner_id"][1] if o["partner_id"] else "?",
                        "tutar": float(o["amount"]),
                        "hesap": o["journal_id"][1] if o["journal_id"] else "?",
                        "tarih": o["date"]} for o in odemeler[:5]],
        }

    async def stok_listesi(self, sirket_id, arama=None, limit=8):
        domain = [("company_id","=",sirket_id),("location_id.usage","=","internal")]
        if arama:
            domain.append(("product_id.name","ilike",arama))
        quantlar = await self._sr("stock.quant", domain,
            ["product_id","quantity","reserved_quantity","location_id"], limit, "quantity asc")
        return [{"urun":    q["product_id"][1] if q["product_id"] else "?",
                 "miktar":  float(q["quantity"]),
                 "rezerve": float(q.get("reserved_quantity",0)),
                 "net":     float(q["quantity"]) - float(q.get("reserved_quantity",0)),
                 "lokasyon":q["location_id"][1] if q["location_id"] else "?"}
                for q in quantlar]

    async def kritik_stok(self, sirket_id):
        kurallar = await self._sr("stock.warehouse.orderpoint",
            [("company_id","=",sirket_id)],
            ["product_id","product_min_qty","qty_on_hand"], 200)
        kritikler = []
        for k in kurallar:
            mevcut  = float(k.get("qty_on_hand",0))
            minimum = float(k.get("product_min_qty",0))
            if mevcut <= minimum:
                kritikler.append({"urun": k["product_id"][1] if k["product_id"] else "?",
                                  "mevcut": mevcut, "minimum": minimum,
                                  "eksik": max(0.0, minimum - mevcut)})
        kritikler.sort(key=lambda x: x["mevcut"])
        return kritikler

    async def cek_senet(self, sirket_id, limit=8):
        odemeler = await self._sr("account.payment",
            [("company_id","=",sirket_id),("state","in",["draft","posted"]),
             ("payment_method_code","in",["check_printing","manual"])],
            ["partner_id","amount","date","payment_type","memo"], limit, "date asc")
        return [{"cari":  o["partner_id"][1] if o["partner_id"] else "?",
                 "tutar": float(o["amount"]),
                 "tarih": o.get("date") or "?",
                 "tip":   "alacak" if o["payment_type"] == "inbound" else "borç",
                 "not":   o.get("memo") or ""}
                for o in odemeler]

    async def sirket_listesi(self):
        return await self._sr("res.company", [("active","=",True)], ["id","name"], 50)
