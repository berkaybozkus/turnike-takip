"""Tarih araligina gore giris-cikis raporu: sayfadaki onizleme ve Excel dosyasi."""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from io import BytesIO
from itertools import groupby
from urllib.parse import urlencode

from fastapi import Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

from app.hesaplama import CIKIS_YOK, EKSIK_OKUTMA, ICERIDE, TAMAM, Okutma, gunu_hesapla
from app.web import GUNLER, korumali, mesaj_birak, sayfa, takip_baglantisi, tam_sayi

EN_FAZLA_GUN = 366
ONIZLEME_SINIRI = 200
DURUMLAR = (ICERIDE, CIKIS_YOK, EKSIK_OKUTMA, TAMAM)
BASLIKLAR = ["Tarih", "Gün", "Sicil No", "Ad Soyad", "Departman", "Giriş", "Çıkış", "Durum", "Not"]
GENISLIKLER = [12, 12, 12, 26, 22, 14, 14, 15, 32]

GIRIS_YOK = "Giriş yok"
CIKIS_OKUTULMAMIS = "Çıkış yok"
HENUZ_CIKMADI = "Henüz çıkmadı"


@dataclass(frozen=True)
class RaporSatiri:
    tarih: date
    sicil_no: str
    ad_soyad: str
    departman: str | None
    giris: datetime | None
    cikis: datetime | None
    giris_metni: str  # giris yoksa hucreye yazilacak metin
    cikis_metni: str  # cikis yoksa hucreye yazilacak metin
    durum: str
    notu: str


def gunu_satirlara_cevir(tarih, sicil_no, ad_soyad, departman, sonuc):
    """Bir kisinin bir gununu, her giris-cikis cifti bir satir olacak sekilde acar."""
    notu = ""
    if sonuc.yonu_bilinmeyen:
        notu = "Yönü bilinmeyen okutma: " + ", ".join(z.strftime("%H:%M") for z in sonuc.yonu_bilinmeyen)

    # Sadece yonu bilinmeyen okutmasi olan gun de raporda bir satirla gorunsun.
    hareketler = sonuc.hareketler or (None,)
    satirlar = []
    for sira, h in enumerate(hareketler):
        son_satir = sira == len(hareketler) - 1
        if h is None:
            giris, cikis, giris_metni, cikis_metni = None, None, "—", "—"
        else:
            giris, cikis = h.giris, h.cikis
            giris_metni = "" if giris else GIRIS_YOK
            cikis_metni = "" if cikis else (HENUZ_CIKMADI if son_satir and sonuc.durum == ICERIDE else CIKIS_OKUTULMAMIS)
        satirlar.append(RaporSatiri(
            tarih, sicil_no, ad_soyad, departman, giris, cikis, giris_metni, cikis_metni,
            sonuc.durum, notu if sira == 0 else "",
        ))
    return satirlar


def rapor_satirlari(cn, bas, bit, departman_id=None, personel_id=None, durum=""):
    """Tarih araligindaki okutmalari tarih ve isim sirasiyla rapor satirlarina cevirir."""
    # Gunluk listenin aksine okutmadan basliyoruz: raporda sadece kaydi olan gunler yer alir.
    sorgu = """
        SELECT p.id, p.sicil_no, p.ad, p.soyad, d.ad AS departman, g.zaman, g.yon, g.cihaz
        FROM gecis g
        JOIN personel p ON p.id = g.personel_id
        LEFT JOIN departman d ON d.id = p.departman_id
        WHERE g.zaman >= ? AND g.zaman < ?
    """
    parametreler = [bas, bit + timedelta(days=1)]
    if departman_id is not None:
        sorgu += " AND p.departman_id = ?"
        parametreler.append(departman_id)
    if personel_id is not None:
        sorgu += " AND p.id = ?"
        parametreler.append(personel_id)
    sorgu += " ORDER BY p.ad, p.soyad, p.id, g.zaman"

    bugun = date.today()
    gunler = []
    kayitlar = cn.execute(sorgu, parametreler).fetchall()
    for (_, gun), grup in groupby(kayitlar, key=lambda k: (k.id, k.zaman.date())):
        grup = list(grup)
        ilk = grup[0]
        sonuc = gunu_hesapla([Okutma(k.zaman, k.yon, k.cihaz) for k in grup], gun == bugun)
        if not durum or sonuc.durum == durum:
            gunler.append((gun, ilk, sonuc))

    # sorted kararlidir: ayni gun icinde isim sirasi korunur.
    gunler.sort(key=lambda g: g[0])
    satirlar = []
    for gun, ilk, sonuc in gunler:
        satirlar += gunu_satirlara_cevir(gun, ilk.sicil_no, f"{ilk.ad} {ilk.soyad}", ilk.departman, sonuc)
    return satirlar


def excel_olustur(satirlar):
    """Rapor satirlarindan .xlsx dosyasinin baytlarini uretir."""
    kitap = Workbook()
    sayfa_ = kitap.active
    sayfa_.title = "Giriş Çıkış"

    baslik_zemin = PatternFill("solid", fgColor="1F5FBF")
    for sutun, baslik in enumerate(BASLIKLAR, start=1):
        hucre = sayfa_.cell(row=1, column=sutun, value=baslik)
        hucre.font = Font(bold=True, color="FFFFFF")
        hucre.fill = baslik_zemin
        hucre.alignment = Alignment(vertical="center")

    kirmizi_zemin = PatternFill("solid", fgColor="FDECEA")
    kirmizi_yazi = Font(color="B3261E", bold=True)
    mavi_yazi = Font(color="1A5A9E")

    def metin_yaz(satir_no, sutun, deger):
        hucre = sayfa_.cell(row=satir_no, column=sutun, value=deger)
        # '=' ile baslayan bir isim Excel'de formul gibi calismasin, duz metin kalsin.
        hucre.data_type = "s"
        return hucre

    def saat_yaz(satir_no, sutun, zaman, metin):
        if zaman is not None:
            hucre = sayfa_.cell(row=satir_no, column=sutun, value=zaman.time())
            hucre.number_format = "hh:mm"
            return
        hucre = metin_yaz(satir_no, sutun, metin)
        if metin == HENUZ_CIKMADI:
            hucre.font = mavi_yazi
        elif metin in (GIRIS_YOK, CIKIS_OKUTULMAMIS):
            hucre.font = kirmizi_yazi
            hucre.fill = kirmizi_zemin

    for satir_no, s in enumerate(satirlar, start=2):
        sayfa_.cell(row=satir_no, column=1, value=s.tarih).number_format = "dd.mm.yyyy"
        metin_yaz(satir_no, 2, GUNLER[s.tarih.weekday()])
        metin_yaz(satir_no, 3, s.sicil_no)
        metin_yaz(satir_no, 4, s.ad_soyad)
        metin_yaz(satir_no, 5, s.departman or "")
        saat_yaz(satir_no, 6, s.giris, s.giris_metni)
        saat_yaz(satir_no, 7, s.cikis, s.cikis_metni)
        metin_yaz(satir_no, 8, s.durum)
        metin_yaz(satir_no, 9, s.notu)

    for sutun, genislik in zip("ABCDEFGHI", GENISLIKLER):
        sayfa_.column_dimensions[sutun].width = genislik
    sayfa_.freeze_panes = "A2"
    sayfa_.auto_filter.ref = f"A1:I{max(len(satirlar) + 1, 1)}"
    sayfa_.page_setup.orientation = "landscape"
    sayfa_.page_setup.fitToWidth = 1
    sayfa_.page_setup.fitToHeight = 0
    sayfa_.sheet_properties.pageSetUpPr.fitToPage = True
    sayfa_.print_title_rows = "1:1"

    cikti = BytesIO()
    kitap.save(cikti)
    return cikti.getvalue()


def _tarih_oku(metin):
    try:
        tarih = date.fromisoformat(metin)
    except ValueError:
        return None
    return tarih if 2000 <= tarih.year <= 2100 else None


def araligi_coz(bas, bit):
    """(baslangic, bitis, hata) dondurur. Tarih verilmezse son 7 gun."""
    bugun = date.today()
    varsayilan = (bugun - timedelta(days=6), bugun)
    if not bas and not bit:
        return *varsayilan, None

    bas_t, bit_t = _tarih_oku(bas), _tarih_oku(bit)
    if bas_t is None or bit_t is None:
        return *varsayilan, "Lütfen geçerli bir başlangıç ve bitiş tarihi girin."
    if bas_t > bit_t:
        return *varsayilan, "Başlangıç tarihi bitiş tarihinden sonra olamaz."
    if (bit_t - bas_t).days + 1 > EN_FAZLA_GUN:
        return *varsayilan, f"Rapor en fazla {EN_FAZLA_GUN} gün için alınabilir."
    return bas_t, bit_t, None


@korumali.get("/rapor", response_class=HTMLResponse)
def rapor(request: Request, bas: str = "", bit: str = "", departman: str = "", personel: str = "", durum: str = ""):
    baslangic, bitis, hata = araligi_coz(bas, bit)
    departman_id, personel_id = tam_sayi(departman), tam_sayi(personel)
    durum = durum if durum in DURUMLAR else ""

    with takip_baglantisi() as cn:
        departmanlar = cn.execute("SELECT id, ad FROM departman ORDER BY ad").fetchall()
        personeller = cn.execute("SELECT id, sicil_no, ad, soyad, aktif FROM personel ORDER BY ad, soyad").fetchall()
        satirlar = [] if hata else rapor_satirlari(cn, baslangic, bitis, departman_id, personel_id, durum)

    suzgec = {"departman": departman_id or "", "personel": personel_id or "", "durum": durum}

    def baglanti(yol, b, s):
        degerler = {"bas": b.isoformat(), "bit": s.isoformat(), **suzgec}
        return f"{yol}?" + urlencode({k: v for k, v in degerler.items() if v != ""})

    bugun = date.today()
    hazir_araliklar = [
        ("Bugün", bugun, bugun),
        ("Son 7 gün", bugun - timedelta(days=6), bugun),
        ("Son 30 gün", bugun - timedelta(days=29), bugun),
        ("Bu ay", bugun.replace(day=1), bugun),
    ]

    return sayfa(request, "rapor.html", {
        "bas": baslangic,
        "bit": bitis,
        "gun_sayisi": (bitis - baslangic).days + 1,
        "en_fazla_gun": EN_FAZLA_GUN,
        "hata": hata,
        "departmanlar": departmanlar,
        "personeller": personeller,
        "durumlar": DURUMLAR,
        "departman_id": departman_id,
        "personel_id": personel_id,
        "durum": durum,
        "hazir": [(ad, baglanti("/rapor", b, s), b == baslangic and s == bitis) for ad, b, s in hazir_araliklar],
        "excel_adresi": baglanti("/rapor/excel", baslangic, bitis),
        "satirlar": satirlar[:ONIZLEME_SINIRI],
        "toplam": len(satirlar),
        "onizleme_siniri": ONIZLEME_SINIRI,
    })


@korumali.get("/rapor/excel")
def rapor_excel(request: Request, bas: str = "", bit: str = "", departman: str = "", personel: str = "", durum: str = ""):
    baslangic, bitis, hata = araligi_coz(bas, bit)
    if hata:
        mesaj_birak(request, "hata", hata)
        return RedirectResponse("/rapor", status_code=303)

    durum = durum if durum in DURUMLAR else ""
    with takip_baglantisi() as cn:
        satirlar = rapor_satirlari(cn, baslangic, bitis, tam_sayi(departman), tam_sayi(personel), durum)

    return Response(
        excel_olustur(satirlar),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="turnike_raporu_{baslangic}_{bitis}.xlsx"'},
    )
