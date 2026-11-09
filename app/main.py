"""Web paneli. Calistirma: baslat.bat"""

import asyncio
import logging
import sqlite3
from collections import Counter
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta
from urllib.parse import urlencode

from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app import ayarlar, rapor, yonetim  # noqa: F401  (sayfalar ice aktarilinca kaydolur)
from app.db import tr_kucuk
from app.guvenlik import GirisSiniri, sifre_dogru
from app.grafik import saatlik_grafik
from app.gunluk import gunluk_liste, manuel_kayitlar, saatlik_hareket, son_hareketler
from app.hesaplama import CIKIS_YOK, EKSIK_OKUTMA, ICERIDE, KAYIT_YOK, TAMAM
from app.senkron import senkronize
from app.web import CsrfHatasi, GirisGerekli, csrf_dogrula, korumali, sayfa, senkron_durumu, takip_baglantisi, tam_sayi
from scripts import kurulum

log = logging.getLogger("turnike")

DURUM_GRUPLARI = {
    "cikmayan": ("Çıkış yapmayanlar", {ICERIDE, CIKIS_YOK}),
    "cikan": ("Çıkış yapan", {TAMAM}),
    "eksik": ("Eksik okutma", {EKSIK_OKUTMA}),
    "kayitsiz": ("Kayıt yok", {KAYIT_YOK}),
}


async def senkron_dongusu():
    while True:
        try:
            # senkronize() engelleyen bir is; ayri is parcaciginda calisir, panel donmaz.
            await asyncio.to_thread(senkronize)
            senkron_durumu.update(son=datetime.now(), hata=False)
        except Exception:
            log.exception("Senkron basarisiz")
            senkron_durumu["hata"] = True
        await asyncio.sleep(ayarlar.SENKRON_ARALIGI)


async def demo_sifirlama_dongusu():
    while True:
        await asyncio.sleep(ayarlar.DEMO_SIFIRLAMA_DAKIKA * 60)
        try:
            await asyncio.to_thread(kurulum.demo_sifirla)
        except Exception:
            log.exception("Demo sifirlama basarisiz")


@asynccontextmanager
async def omur(_app):
    # Ilk acilista veritabani dosyalarini ve demo verisini olusturur; sonra bir sey yapmaz.
    await asyncio.to_thread(kurulum.main)
    gorevler = [asyncio.create_task(senkron_dongusu())]
    if ayarlar.CANLI_DEMO:
        gorevler.append(asyncio.create_task(demo_sifirlama_dongusu()))
    yield
    for gorev in gorevler:
        gorev.cancel()


app = FastAPI(title="Turnike Takip", lifespan=omur, docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(
    SessionMiddleware, secret_key=ayarlar.OTURUM_ANAHTARI, same_site="lax", max_age=8 * 3600, https_only=ayarlar.CANLI_DEMO
)
giris_siniri = GirisSiniri()
app.mount("/static", StaticFiles(directory=ayarlar.KOK / "app" / "static"), name="static")


@app.exception_handler(GirisGerekli)
def giris_sayfasina_yonlendir(_request, _hata):
    return RedirectResponse("/giris", status_code=303)


@app.exception_handler(CsrfHatasi)
def csrf_hatasi(_request, _hata):
    return HTMLResponse('<h1>Oturum doğrulanamadı</h1><p>Sayfayı yenileyip tekrar deneyin. <a href="/">Ana sayfa</a></p>', status_code=403)


@app.exception_handler(sqlite3.Error)
def veritabani_hatasi(_request, hata):
    log.error("Veritabani hatasi: %s", hata)
    return HTMLResponse("<h1>Veritabanına ulaşılamadı</h1><p>Lütfen biraz sonra yeniden deneyin.</p>", status_code=503)


@app.get("/giris", response_class=HTMLResponse)
def giris_formu(request: Request):
    if request.session.get("kullanici"):
        return RedirectResponse("/", status_code=303)
    return sayfa(request, "giris.html")


@app.post("/giris", response_class=HTMLResponse, dependencies=[Depends(csrf_dogrula)])
def giris_yap(request: Request, kullanici_adi: str = Form(""), sifre: str = Form("")):
    # Anahtar IP ile birlikte: saldirgan baska birinin hesabini kilitleyemez.
    anahtar = (request.client.host if request.client else "?", tr_kucuk(kullanici_adi.strip())[:50])
    kalan = giris_siniri.kalan_saniye(anahtar)
    if kalan:
        dakika = max(1, round(kalan / 60))
        hata = f"Çok fazla hatalı deneme. Lütfen {dakika} dakika sonra tekrar deneyin."
        return sayfa(request, "giris.html", {"hata": hata, "kullanici_adi": kullanici_adi}, 429)

    with takip_baglantisi() as cn:
        kayitli = cn.execute(
            "SELECT sifre_ozeti FROM kullanici WHERE kullanici_adi = ? AND aktif = 1", kullanici_adi
        ).fetchval()

    if not sifre_dogru(sifre, kayitli):
        giris_siniri.hatali(anahtar)
        return sayfa(request, "giris.html", {"hata": "Kullanıcı adı veya şifre hatalı.", "kullanici_adi": kullanici_adi}, 401)

    giris_siniri.sifirla(anahtar)
    # Oturum yenilenir: giristen onceki CSRF jetonu gecersiz olur.
    request.session.clear()
    request.session["kullanici"] = kullanici_adi
    return RedirectResponse("/", status_code=303)


@korumali.post("/cikis")
def cikis_yap(request: Request):
    request.session.clear()
    return RedirectResponse("/giris", status_code=303)


def tarihi_coz(metin):
    try:
        tarih = date.fromisoformat(metin)
    except ValueError:
        return date.today()
    # Uc tarihlerde onceki/sonraki gun hesabi tasmasin.
    return tarih if 2000 <= tarih.year <= 2100 else date.today()


@korumali.get("/", response_class=HTMLResponse)
def gunluk(request: Request, tarih: str = "", departman: str = "", ara: str = "", durum: str = ""):
    secilen = tarihi_coz(tarih)
    departman_id = tam_sayi(departman)
    ara = ara.strip()[:100]

    with takip_baglantisi() as cn:
        departmanlar = cn.execute("SELECT id, ad FROM departman ORDER BY ad").fetchall()
        satirlar = gunluk_liste(cn, secilen, departman_id, ara)
        personeller = cn.execute("SELECT id, sicil_no, ad, soyad FROM personel WHERE aktif = 1 ORDER BY ad, soyad").fetchall()
        grafik = saatlik_grafik(saatlik_hareket(cn, secilen, departman_id))
        son = son_hareketler(cn, secilen, departman_id)
        manuel = manuel_kayitlar(cn, secilen)

    durum = durum if durum in DURUM_GRUPLARI else ""

    def baglanti(**degisen):
        degerler = {"tarih": secilen.isoformat(), "departman": departman_id or "", "ara": ara, "durum": durum, **degisen}
        return "/?" + urlencode({k: v for k, v in degerler.items() if v != ""})

    sayilar = Counter(s.sonuc.durum for s in satirlar)
    secimler = [("Tümü", "", len(satirlar))] + [
        (ad, kod, sum(sayilar[d] for d in grup)) for kod, (ad, grup) in DURUM_GRUPLARI.items()
    ]
    giris_yapan = sum(any(h.giris for h in s.sonuc.hareketler) for s in satirlar)
    ozetler = [
        ("Kayıtlı personel", len(satirlar), "Listede görünen personel", "personel", "notr"),
        ("Giriş yapan", giris_yapan, "Bugün kart okutan" if secilen == date.today() else "O gün kart okutan", "giris", "yesil"),
        ("Çıkış yapan", sayilar[TAMAM], "Çıkışı tamamlanan", "cikis", "mavi"),
        ("Kayıt bulunmayan", sayilar[KAYIT_YOK], "Okutması olmayan", "uyari", "sari"),
    ]
    excel = {"bas": secilen.isoformat(), "bit": secilen.isoformat(), "departman": departman_id or ""}

    return sayfa(request, "gunluk.html", {
        "ozetler": ozetler,
        "grafik": grafik,
        "son_hareketler": son,
        "manuel_kayitlar": manuel,
        "personeller": personeller,
        "suan": datetime.now().strftime("%H:%M") if secilen == date.today() else "",
        "excel_adresi": "/rapor/excel?" + urlencode({k: v for k, v in excel.items() if v != ""}),
        "tarih": secilen,
        "bugun": date.today(),
        "onceki": baglanti(tarih=(secilen - timedelta(days=1)).isoformat()),
        "sonraki": baglanti(tarih=(secilen + timedelta(days=1)).isoformat()),
        "bugune_don": baglanti(tarih=date.today().isoformat()),
        "departmanlar": departmanlar,
        "departman_id": departman_id,
        "ara": ara,
        "durum": durum,
        "secimler": [(ad, deger, adet, baglanti(durum=deger)) for ad, deger, adet in secimler],
        "satirlar": [s for s in satirlar if not durum or s.sonuc.durum in DURUM_GRUPLARI[durum][1]],
    })


app.include_router(korumali)
