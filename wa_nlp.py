

def nlp_tablolari_olustur(engine):
    """whatsapp_bi.py'deki tablolari_olustur'dan çağrılır."""
    try:
        WaNlpDeneyim.__table__.create(bind=engine, checkfirst=True)
        WaNlpDogrulama.__table__.create(bind=engine, checkfirst=True)
        import logging
        logging.getLogger("wa_nlp").info("wa_nlp tabloları hazır")
    except Exception as e:
        logging.getLogger("wa_nlp").warning(f"wa_nlp tablo oluşturma: {e}")
