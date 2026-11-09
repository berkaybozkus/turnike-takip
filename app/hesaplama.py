"""Bir kisinin bir gunluk okutmalarini giris-cikis ciftlerine ayirir.

Veritabanina dokunmaz; bu sayede veritabani olmadan test edilebilir.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

# Ayni yonde bu sure icindeki ikinci okutma, ayni gecis sayilir.
CIFT_OKUTMA_ESIGI = timedelta(seconds=60)

KAYIT_YOK = "Kayıt yok"
TAMAM = "Tamam"
ICERIDE = "İçeride"
CIKIS_YOK = "Çıkış yok"
EKSIK_OKUTMA = "Eksik okutma"


@dataclass(frozen=True)
class Okutma:
    zaman: datetime
    yon: str | None  # 'G', 'C' veya None
    cihaz: str | None = None


@dataclass(frozen=True)
class GirisCikis:
    giris: datetime | None  # None: cikis var ama girisi okutulmamis
    cikis: datetime | None  # None: giris var ama cikisi okutulmamis


@dataclass(frozen=True)
class GunSonucu:
    hareketler: tuple[GirisCikis, ...]
    yonu_bilinmeyen: tuple[datetime, ...]
    durum: str


def cift_okutmalari_ayikla(sirali):
    temiz = []
    for okutma in sirali:
        onceki = temiz[-1] if temiz else None
        if onceki and okutma.yon == onceki.yon and okutma.zaman - onceki.zaman <= CIFT_OKUTMA_ESIGI:
            continue
        temiz.append(okutma)
    return temiz


def gunu_hesapla(okutmalar, bugun_mu=False):
    """Okutmalari zaman sirasina gore giris-cikis ciftlerine ayirir."""
    temiz = cift_okutmalari_ayikla(sorted(okutmalar, key=lambda o: o.zaman))

    hareketler = []
    yonu_bilinmeyen = []
    acik_giris = None  # cikisi henuz gorulmemis giris

    for okutma in temiz:
        if okutma.yon == "G":
            if acik_giris is not None:  # onceki giristen cikis okutulmamis
                hareketler.append(GirisCikis(acik_giris, None))
            acik_giris = okutma.zaman
        elif okutma.yon == "C":
            hareketler.append(GirisCikis(acik_giris, okutma.zaman))
            acik_giris = None
        else:
            yonu_bilinmeyen.append(okutma.zaman)

    if acik_giris is not None:
        hareketler.append(GirisCikis(acik_giris, None))

    if not temiz:
        durum = KAYIT_YOK
    elif acik_giris is not None:
        durum = ICERIDE if bugun_mu else CIKIS_YOK
    elif yonu_bilinmeyen or any(h.giris is None or h.cikis is None for h in hareketler):
        durum = EKSIK_OKUTMA
    else:
        durum = TAMAM

    return GunSonucu(tuple(hareketler), tuple(yonu_bilinmeyen), durum)
