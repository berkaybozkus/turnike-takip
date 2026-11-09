"""Tum sayfalarin ortak kullandigi parcalar: sablonlar, oturum kontrolu, baglanti."""

import hmac
import secrets
from contextlib import closing

from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates

from app import ayarlar
from app.db import baglan
from app.hesaplama import CIKIS_YOK, EKSIK_OKUTMA, ICERIDE, KAYIT_YOK, TAMAM

AYLAR = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz",
         "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
GUNLER = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]
DURUM_SINIFI = {TAMAM: "tamam", ICERIDE: "iceride", CIKIS_YOK: "cikis-yok", EKSIK_OKUTMA: "eksik", KAYIT_YOK: "kayit-yok"}

# Aktif karti olmayan okutmalar. Karti sonradan tanimlanmis eski kayitlar burada gorunmez.
TANIMSIZ_KOSUL = """
    g.personel_id IS NULL
    AND NOT EXISTS (SELECT 1 FROM kart k WHERE k.kart_no = g.kart_no AND k.aktif = 1)
"""

senkron_durumu = {"son": None, "hata": False}

sablonlar = Jinja2Templates(directory=ayarlar.KOK / "app" / "templates")
sablonlar.env.filters["saat"] = lambda z: z.strftime("%H:%M")
sablonlar.env.filters["tarih_saat"] = lambda z: z.strftime("%d.%m.%Y %H:%M")
sablonlar.env.filters["uzun_tarih"] = lambda t: f"{t.day} {AYLAR[t.month - 1]} {t.year}, {GUNLER[t.weekday()]}"
sablonlar.env.filters["durum_sinifi"] = lambda d: DURUM_SINIFI.get(d, "")


def _bas_harfler(ad_soyad):
    """'Ayşe Yılmaz' -> 'AY' (Turkce buyuk harfle)."""
    harfler = "".join(p[0] for p in ad_soyad.split()[:2])
    return harfler.replace("i", "İ").replace("ı", "I").upper()


sablonlar.env.filters["bas_harfler"] = _bas_harfler


class GirisGerekli(Exception):
    pass


class CsrfHatasi(Exception):
    pass


def oturum_gerekli(request: Request):
    if not request.session.get("kullanici"):
        raise GirisGerekli


def csrf_jetonu(request):
    """Oturuma ozel gizli deger. Her POST formu bunu geri gondermek zorunda."""
    if "csrf" not in request.session:
        request.session["csrf"] = secrets.token_urlsafe(32)
    return request.session["csrf"]


async def csrf_dogrula(request: Request):
    """Baska bir sitenin kullanicinin oturumuyla form gondermesini engeller."""
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return
    gelen = str((await request.form()).get("csrf_token", ""))
    beklenen = request.session.get("csrf")
    if not beklenen or not hmac.compare_digest(gelen.encode(), beklenen.encode()):
        raise CsrfHatasi


# Bu router'a eklenen her sayfa otomatik olarak giris ve CSRF denetimi ister.
korumali = APIRouter(dependencies=[Depends(oturum_gerekli), Depends(csrf_dogrula)])


def takip_baglantisi():
    return closing(baglan(ayarlar.TAKIP_DB))


def tam_sayi(metin):
    """Formdan gelen metni sayiya cevirir; gecersizse None."""
    return int(metin) if metin.isdecimal() and len(metin) < 10 else None


def mesaj_birak(request, tur, metin):
    """Bir sonraki sayfada bir kez gosterilecek mesaj. tur: 'basari' veya 'hata'."""
    request.session["mesaj"] = {"tur": tur, "metin": metin}


def sayfa(request, ad, baglam=None, durum_kodu=200):
    kullanici = request.session.get("kullanici")
    tanimsiz_kart = 0
    if kullanici:
        with takip_baglantisi() as cn:
            tanimsiz_kart = cn.execute(f"SELECT COUNT(DISTINCT g.kart_no) FROM gecis g WHERE {TANIMSIZ_KOSUL}").fetchval()

    icerik = {
        "kullanici": kullanici,
        "senkron": senkron_durumu,
        "tanimsiz_kart": tanimsiz_kart,
        "demo_mod": not ayarlar.KAYNAK_ODBC,
        "canli_demo": ayarlar.CANLI_DEMO,
        "sifirlama_dakika": ayarlar.DEMO_SIFIRLAMA_DAKIKA,
        "csrf": csrf_jetonu(request),
        "mesaj": request.session.pop("mesaj", None),
        **(baglam or {}),
    }
    return sablonlar.TemplateResponse(request, ad, icerik, status_code=durum_kodu)
