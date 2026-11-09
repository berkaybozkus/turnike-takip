from datetime import date, datetime, time, timedelta
from io import BytesIO

from openpyxl import load_workbook

from app.hesaplama import ICERIDE, Okutma, gunu_hesapla
from app.rapor import EN_FAZLA_GUN, araligi_coz, excel_olustur, gunu_satirlara_cevir

GUN = date(2026, 11, 4)


def z(saat, dakika=0):
    return datetime(2026, 11, 4, saat, dakika)


def satirlar(*okutmalar, bugun_mu=False, ad="Ayşe Yılmaz"):
    sonuc = gunu_hesapla([Okutma(zaman, yon) for zaman, yon in okutmalar], bugun_mu)
    return gunu_satirlara_cevir(GUN, "S0001", ad, "Muhasebe", sonuc)


def excel_sayfasi(rapor):
    return load_workbook(BytesIO(excel_olustur(rapor))).active


def test_her_cift_ayri_satir_cikisi_olmayan_isaretli():
    r = satirlar((z(8, 30), "G"), (z(13), "C"), (z(14), "G"))
    assert len(r) == 2
    assert (r[0].giris, r[0].cikis) == (z(8, 30), z(13))
    assert (r[1].giris, r[1].cikis, r[1].cikis_metni) == (z(14), None, "Çıkış yok")


def test_bugun_acik_giris_henuz_cikmadi():
    r = satirlar((z(8, 30), "G"), bugun_mu=True)
    assert r[0].cikis_metni == "Henüz çıkmadı"
    assert r[0].durum == ICERIDE


def test_gun_ortasindaki_eksik_cikis_bugun_de_cikis_yok():
    r = satirlar((z(8), "G"), (z(10), "G"), bugun_mu=True)
    assert r[0].cikis_metni == "Çıkış yok"
    assert r[1].cikis_metni == "Henüz çıkmadı"


def test_sadece_yonu_bilinmeyen_gun_de_satir_uretir():
    r = satirlar((z(9), None))
    assert len(r) == 1
    assert r[0].giris_metni == "—"
    assert "09:00" in r[0].notu


def test_excel_basliklar_ve_gercek_saat_degerleri():
    s = excel_sayfasi(satirlar((z(8, 30), "G"), (z(18, 30), "C")))
    assert [h.value for h in s[1]] == ["Tarih", "Gün", "Sicil No", "Ad Soyad", "Departman", "Giriş", "Çıkış", "Durum", "Not"]
    assert s["A2"].value.date() == GUN
    assert s["A2"].number_format == "dd.mm.yyyy"
    assert s["B2"].value == "Çarşamba"
    assert s["F2"].value == time(8, 30)
    assert s["F2"].number_format == "hh:mm"
    assert s["G2"].value == time(18, 30)


def test_excel_cikis_yok_metin_ve_kirmizi():
    s = excel_sayfasi(satirlar((z(8, 30), "G")))
    assert s["G2"].value == "Çıkış yok"
    assert s["G2"].font.color.rgb.endswith("B3261E")


def test_excel_formul_gibi_isim_duz_metin_kalir():
    s = excel_sayfasi(satirlar((z(8, 30), "G"), ad="=HYPERLINK(1)"))
    assert s["D2"].value == "=HYPERLINK(1)"
    assert s["D2"].data_type == "s"


def test_excel_bos_rapor_sadece_baslik():
    s = excel_sayfasi([])
    assert s.max_row == 1


def test_aralik_varsayilan_son_7_gun():
    bas, bit, hata = araligi_coz("", "")
    assert hata is None
    assert bit == date.today()
    assert (bit - bas).days == 6


def test_aralik_hatalari():
    assert araligi_coz("bozuk", "2026-11-01")[2]
    assert araligi_coz("2026-11-02", "2026-11-01")[2]
    assert araligi_coz("0001-01-01", "2026-11-01")[2]


def test_aralik_sinir_degeri():
    bit = date(2026, 12, 31)
    izinli = bit - timedelta(days=EN_FAZLA_GUN - 1)
    assert araligi_coz(izinli.isoformat(), bit.isoformat())[2] is None
    assert araligi_coz((izinli - timedelta(days=1)).isoformat(), bit.isoformat())[2]
