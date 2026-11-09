"""Turnike veritabanindaki yeni okutmalari takip veritabanina aktarir.

Kaynaktan sadece okur. Calistirma: python -m app.senkron
"""

import threading
from contextlib import closing

from app import ayarlar
from app.db import baglan

PARTI_BOYUTU = 1000

# Kart tanimlama ile senkronun ayni anda calismasini engeller.
senkron_kilidi = threading.Lock()

# Manuel kayitlarin kaynak_id degeri negatiftir; senkronun kaldigi yeri etkilemez.
SON_ID_SORGUSU = "SELECT COALESCE(MAX(kaynak_id), 0) FROM gecis WHERE kaynak_id > 0"
AKTIF_KART_SORGUSU = "SELECT kart_no, personel_id FROM kart WHERE aktif = 1"
GECIS_EKLE = """
    INSERT INTO gecis (kaynak_id, kart_no, personel_id, zaman, yon, cihaz)
    VALUES (?, ?, ?, ?, ?, ?)
"""


def kaynak_baglan():
    if ayarlar.KAYNAK_ODBC:
        import pyodbc  # sadece harici SQL Server kaynagi kullanilirsa gerekir

        return pyodbc.connect(ayarlar.KAYNAK_ODBC)
    return baglan(ayarlar.KAYNAK_DB)


def yonu_duzelt(deger):
    """Kaynaktan gelen yonu 'G' veya 'C' yapar; anlasilmayan degerler None olur."""
    yon = (deger or "").strip().upper()
    return yon if yon in ("G", "C") else None


def gecis_satiri(kaynak_satiri, kartlar):
    """Kaynak satirini gecis tablosuna yazilacak hale getirir."""
    kaynak_id, kart_no, zaman, yon, cihaz = kaynak_satiri
    kart_no = str(kart_no).strip()
    # .get: kart tanimli degilse hata vermez, None dondurur (personel_id NULL olur).
    return (kaynak_id, kart_no, kartlar.get(kart_no), zaman.replace(microsecond=0), yonu_duzelt(yon), cihaz)


def senkronize():
    """Yeni kayitlari aktarir ve aktarilan kayit sayisini dondurur."""
    kaynak_sorgusu = (ayarlar.KOK / "sql" / "kaynak_sorgu.sql").read_text(encoding="utf-8")

    with senkron_kilidi, closing(baglan(ayarlar.TAKIP_DB)) as takip, closing(kaynak_baglan()) as kaynak:
        son_id = takip.execute(SON_ID_SORGUSU).fetchval()
        kartlar = {kart_no: personel_id for kart_no, personel_id in takip.execute(AKTIF_KART_SORGUSU).fetchall()}

        imlec = kaynak.execute(kaynak_sorgusu, son_id)
        toplam = 0
        while parti := imlec.fetchmany(PARTI_BOYUTU):
            takip.executemany(GECIS_EKLE, [gecis_satiri(satir, kartlar) for satir in parti])
            # Her parti ayri kaydedilir: yarida kesilirse bir sonraki calisma kaldigi yerden devam eder.
            takip.commit()
            toplam += len(parti)

    return toplam


if __name__ == "__main__":
    print(f"{senkronize()} yeni kayit aktarildi.")
