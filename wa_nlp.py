import re
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

log_nlp = logging.getLogger("wa_nlp")

@dataclass
class NLPSonuc:
    intent: str = "bilinmiyor"
    params: dict = field(default_factory=dict)
    kaynak: str = "regex"
    sure_ms: float = 0
    deneyim_id: Optional[int] = None

INTENT_KURALLARI = [
    (["özet", "genel durum", "durum"],                          "ozet"),
    (["banka", "banka bakiye", "hesap"],                        "banka_bakiye"),
    (["kasa", "kasa bakiye", "nakit"],                          "kasa_bakiye"),
    (["cari", "müşteri", "tedarikçi"],                          "cari_listesi"),
    (["fatura", "açık fatura", "borç"],                         "acik_faturalar"),
    (["bugün satış", "günlük satış", "satış", "satis"],         "bugun_satis"),
    (["tahsilat", "ödeme", "tahsil"],                           "tahsilat_durum"),
    (["stok", "stok listesi", "envanter"],                      "stok_listesi"),
    (["kritik stok", "az stok", "biten stok"],                  "kritik_stok"),
    (["çek", "senet", "çek senet"],                             "cek_senet"),
    (["yardım", "yardim", "komut", "ne yapabilirsin", "?"],     "yardim"),
]

class NLPKatmani:
    def __init__(self, db=None, sirket_id=None):
        self.db = db
        self.sirket_id = sirket_id

    async def coz(self, metin: str) -> NLPSonuc:
        t0 = time.time()
        metin_lower = metin.lower().strip()
        for anahtar_kelimeler, intent in INTENT_KURALLARI:
            for kelime in anahtar_kelimeler:
                if kelime in metin_lower:
                    sure = (time.time() - t0) * 1000
                    log_nlp.info(f"Intent: {intent} [{kelime}] {sure:.1f}ms")
                    return NLPSonuc(intent=intent, kaynak="regex", sure_ms=sure)
        sure = (time.time() - t0) * 1000
        return NLPSonuc(intent="bilinmiyor", kaynak="regex", sure_ms=sure)

    @staticmethod
    def negatif_sinyal_mi(metin: str) -> bool:
        negatifler = ["yanlış", "hayır", "değil", "olmadı", "hata"]
        metin_lower = metin.lower()
        return any(n in metin_lower for n in negatifler)

    def dogrulama_sinyali(self, deneyim_id: int, sinyal: str):
        pass  # İleride DB'ye yazılacak

def nlp_tablolari_olustur(engine):
    log_nlp.info("wa_nlp tabloları hazır (basit mod)")
