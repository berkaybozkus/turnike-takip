"""Gunluk giris-cikis listesini veritabanindan okur."""

from dataclasses import dataclass
from datetime import date, timedelta
from itertools import groupby

from app.db import tr_kucuk
from app.hesaplama import GunSonucu, Okutma, gunu_hesapla

# Elle girilen kayitlar bu kart degeri ve negatif kaynak_id ile turnike verisinden ayrilir.
MANUEL_KART = "MANUEL"

ARAMA_KOSULU = r" AND (tr_kucuk(p.ad || ' ' || p.soyad) LIKE ? ESCAPE '\' OR tr_kucuk(p.sicil_no) LIKE ? ESCAPE '\')"


@dataclass(frozen=True)
class GunSatiri:
    personel_id: int
    sicil_no: str
    ad_soyad: str
    departman: str | None
    sonuc: GunSonucu


def saatlik_hareket(cn, tarih, departman_id=None):
    """{saat: (giris, cikis)} dondurur."""
    sorgu = """
        SELECT CAST(strftime('%H', g.zaman) AS INTEGER) AS saat, g.yon, COUNT(*) AS adet
        FROM gecis g JOIN personel p ON p.id = g.personel_id
        WHERE g.zaman >= ? AND g.zaman < ? AND g.yon IS NOT NULL
    """
    parametreler = [tarih, tarih + timedelta(days=1)]
    if departman_id is not None:
        sorgu += " AND p.departman_id = ?"
        parametreler.append(departman_id)
    sorgu += " GROUP BY saat, g.yon"

    sayilar = {}
    for k in cn.execute(sorgu, parametreler).fetchall():
        giris, cikis = sayilar.get(k.saat, (0, 0))
        sayilar[k.saat] = (giris + k.adet, cikis) if k.yon == "G" else (giris, cikis + k.adet)
    return sayilar


def son_hareketler(cn, tarih, departman_id=None, adet=6):
    """Secilen gunun en yeni okutmalarini dondurur."""
    sorgu = """
        SELECT g.zaman, g.yon, g.cihaz, p.ad, p.soyad
        FROM gecis g JOIN personel p ON p.id = g.personel_id
        WHERE g.zaman >= ? AND g.zaman < ?
    """
    parametreler = [tarih, tarih + timedelta(days=1)]
    if departman_id is not None:
        sorgu += " AND p.departman_id = ?"
        parametreler.append(departman_id)
    sorgu += " ORDER BY g.zaman DESC, g.id DESC LIMIT ?"
    return cn.execute(sorgu, parametreler + [adet]).fetchall()


def manuel_kayitlar(cn, tarih):
    """Secilen gun elle girilmis kayitlar."""
    return cn.execute(
        """
        SELECT g.id, g.zaman, g.yon, g.cihaz, p.ad, p.soyad
        FROM gecis g JOIN personel p ON p.id = g.personel_id
        WHERE g.kaynak_id < 0 AND g.kart_no = ? AND g.zaman >= ? AND g.zaman < ?
        ORDER BY g.zaman, g.id
        """,
        MANUEL_KART, tarih, tarih + timedelta(days=1),
    ).fetchall()


def arama_deseni(metin):
    """Aramayi LIKE desenine cevirir; % ve _ joker gibi davranmaz."""
    kacisli = tr_kucuk(metin).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{kacisli}%"


def gunluk_liste(cn, tarih, departman_id=None, arama=""):
    """Secilen gun icin her personelin giris-cikis ozetini dondurur."""
    # LEFT JOIN: o gun hic okutmasi olmayan personel de listede gorunsun.
    sorgu = """
        SELECT p.id, p.sicil_no, p.ad, p.soyad, d.ad AS departman, g.zaman, g.yon, g.cihaz
        FROM personel p
        LEFT JOIN departman d ON d.id = p.departman_id
        LEFT JOIN gecis g ON g.personel_id = p.id AND g.zaman >= ? AND g.zaman < ?
        WHERE (p.aktif = 1 OR g.id IS NOT NULL)
    """
    parametreler = [tarih, tarih + timedelta(days=1)]

    if departman_id is not None:
        sorgu += " AND p.departman_id = ?"
        parametreler.append(departman_id)
    if arama:
        desen = arama_deseni(arama)
        sorgu += ARAMA_KOSULU
        parametreler += [desen, desen]

    sorgu += " ORDER BY p.ad, p.soyad, p.id, g.zaman"

    bugun_mu = tarih == date.today()
    satirlar = []
    for _, grup in groupby(cn.execute(sorgu, parametreler).fetchall(), key=lambda s: s.id):
        kayitlar = list(grup)
        ilk = kayitlar[0]
        okutmalar = [Okutma(k.zaman, k.yon, k.cihaz) for k in kayitlar if k.zaman is not None]
        satirlar.append(
            GunSatiri(ilk.id, ilk.sicil_no, f"{ilk.ad} {ilk.soyad}", ilk.departman, gunu_hesapla(okutmalar, bugun_mu))
        )
    return satirlar
