from datetime import datetime

from app.hesaplama import (
    CIKIS_YOK,
    EKSIK_OKUTMA,
    ICERIDE,
    KAYIT_YOK,
    TAMAM,
    GirisCikis,
    Okutma,
    gunu_hesapla,
)


def z(saat):
    parcalar = [int(p) for p in saat.split(":")]
    return datetime(2026, 11, 4, *parcalar)


def okutmalar(*ciftler):
    return [Okutma(z(saat), yon) for saat, yon in ciftler]


def test_giris_cikis_giris_son_cikis_bos_gorunur():
    s = gunu_hesapla(okutmalar(("08:30", "G"), ("13:00", "C"), ("14:00", "G")))
    assert s.hareketler == (GirisCikis(z("08:30"), z("13:00")), GirisCikis(z("14:00"), None))
    assert s.durum == CIKIS_YOK


def test_ayni_durum_bugunse_iceride():
    s = gunu_hesapla(okutmalar(("08:30", "G"), ("13:00", "C"), ("14:00", "G")), bugun_mu=True)
    assert s.hareketler[-1] == GirisCikis(z("14:00"), None)
    assert s.durum == ICERIDE


def test_molada_cikan_tam_gun():
    s = gunu_hesapla(okutmalar(("08:30", "G"), ("13:00", "C"), ("14:00", "G"), ("18:30", "C")))
    assert s.hareketler == (GirisCikis(z("08:30"), z("13:00")), GirisCikis(z("14:00"), z("18:30")))
    assert s.durum == TAMAM


def test_cift_okutma_tek_sayilir():
    s = gunu_hesapla(okutmalar(("08:30", "G"), ("08:30:10", "G"), ("18:30", "C")))
    assert s.hareketler == (GirisCikis(z("08:30"), z("18:30")),)
    assert s.durum == TAMAM


def test_sadece_cikis_girisi_bos_gorunur():
    s = gunu_hesapla(okutmalar(("17:30", "C")))
    assert s.hareketler == (GirisCikis(None, z("17:30")),)
    assert s.durum == EKSIK_OKUTMA


def test_gun_ortasinda_unutulan_cikis_ayri_satir_olur():
    s = gunu_hesapla(okutmalar(("08:00", "G"), ("10:00", "G"), ("12:00", "C")))
    assert s.hareketler == (GirisCikis(z("08:00"), None), GirisCikis(z("10:00"), z("12:00")))
    assert s.durum == EKSIK_OKUTMA


def test_yonu_bilinmeyen_okutma_kaybolmaz():
    s = gunu_hesapla(okutmalar(("08:00", None), ("17:00", "C")))
    assert s.yonu_bilinmeyen == (z("08:00"),)
    assert s.hareketler == (GirisCikis(None, z("17:00")),)
    assert s.durum == EKSIK_OKUTMA


def test_sira_karisik_gelse_de_dogru_eslesir():
    s = gunu_hesapla(okutmalar(("17:00", "C"), ("08:00", "G")))
    assert s.hareketler == (GirisCikis(z("08:00"), z("17:00")),)
    assert s.durum == TAMAM


def test_okutma_yok():
    s = gunu_hesapla([])
    assert s.hareketler == ()
    assert s.durum == KAYIT_YOK


def test_girissiz_cikistan_sonra_normal_gun():
    s = gunu_hesapla(okutmalar(("08:00", "C"), ("08:30", "G"), ("18:30", "C")))
    assert s.hareketler == (GirisCikis(None, z("08:00")), GirisCikis(z("08:30"), z("18:30")))
    assert s.durum == EKSIK_OKUTMA