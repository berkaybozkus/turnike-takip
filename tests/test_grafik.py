from app.grafik import saatlik_grafik


def test_hareket_yoksa_grafik_yok():
    assert saatlik_grafik({}) is None
    assert saatlik_grafik({9: (0, 0)}) is None


def test_varsayilan_saat_araligi_ve_toplamlar():
    g = saatlik_grafik({8: (10, 0), 18: (1, 9)})
    assert g["gruplar"][0]["saat"] == "07:00"
    assert g["gruplar"][-1]["saat"] == "20:00"
    assert (g["toplam_giris"], g["toplam_cikis"]) == (11, 9)
    assert [t["saat"] for t in g["tablo"]] == ["08:00", "18:00"]


def test_aralik_disindaki_saatler_kaybolmaz():
    g = saatlik_grafik({2: (1, 0), 23: (0, 1)})
    assert g["gruplar"][0]["saat"] == "02:00"
    assert g["gruplar"][-1]["saat"] == "23:00"


def test_eksen_en_buyuk_degeri_kapsar_ve_cubuklar_sinirda_kalir():
    g = saatlik_grafik({8: (17, 0)})
    assert g["kilavuzlar"][-1]["deger"] >= 17
    assert len(g["kilavuzlar"]) <= 5
    assert g["kilavuzlar"][-1]["y"] >= 0


def test_sifir_olan_seri_cubuk_cizmez_ve_zirve_etiketi_var():
    g = saatlik_grafik({8: (4, 0)})
    grup = next(x for x in g["gruplar"] if x["saat"] == "08:00")
    assert [c["seri"] for c in grup["cubuklar"]] == ["giris"]
    assert [z["deger"] for z in g["zirveler"]] == [4]
