"""Saatlik giris-cikis grafiginin geometrisini hesaplar. Sablon sadece cizer."""

from math import ceil

GENISLIK = 320
YUKSEKLIK = 170
SOL, SAG, UST, ALT = 24, 4, 16, 22
EN_ERKEN, EN_GEC = 7, 20  # veri bu saatlerin disina tasarsa aralik genisler
CUBUK = 7
CUBUK_ARASI = 2


def _eksen(en_buyuk):
    """(adim, ust sinir): en fazla 4 aralikli, yuvarlak bir eksen."""
    for adim in (1, 2, 5, 10, 20, 50, 100, 200, 500, 1000):
        if ceil(en_buyuk / adim) <= 4:
            return adim, adim * ceil(en_buyuk / adim)
    return en_buyuk, en_buyuk


def _cubuk_yolu(x, y, genislik, taban):
    """Ustu yuvarlak, tabani duz cubuk."""
    r = min(3, genislik / 2, taban - y)
    return (
        f"M{x:.1f},{taban:.1f}V{y + r:.1f}Q{x:.1f},{y:.1f} {x + r:.1f},{y:.1f}"
        f"H{x + genislik - r:.1f}Q{x + genislik:.1f},{y:.1f} {x + genislik:.1f},{y + r:.1f}V{taban:.1f}Z"
    )


def saatlik_grafik(sayilar):
    """{saat: (giris, cikis)} sozlugunden cizim verisi uretir; hareket yoksa None."""
    sayilar = {s: d for s, d in sayilar.items() if d[0] or d[1]}
    if not sayilar:
        return None

    ilk, son = min(EN_ERKEN, *sayilar), max(EN_GEC, *sayilar)
    saatler = list(range(ilk, son + 1))
    en_buyuk = max(max(d) for d in sayilar.values())
    adim, ust_sinir = _eksen(en_buyuk)

    taban = YUKSEKLIK - ALT
    cizim_yuksekligi = taban - UST
    bant = (GENISLIK - SOL - SAG) / len(saatler)
    y_konumu = lambda deger: taban - cizim_yuksekligi * deger / ust_sinir

    gruplar, zirveler = [], {}
    for sira, saat in enumerate(saatler):
        giris, cikis = sayilar.get(saat, (0, 0))
        x = SOL + sira * bant
        baslangic = x + (bant - 2 * CUBUK - CUBUK_ARASI) / 2
        cubuklar = []
        for seri, deger, cubuk_x in (("giris", giris, baslangic), ("cikis", cikis, baslangic + CUBUK + CUBUK_ARASI)):
            if deger:
                cubuklar.append({"seri": seri, "yol": _cubuk_yolu(cubuk_x, y_konumu(deger), CUBUK, taban)})
                if deger > zirveler.get(seri, {"deger": 0})["deger"]:
                    zirveler[seri] = {"deger": deger, "x": cubuk_x + CUBUK / 2, "y": y_konumu(deger) - 3}
        gruplar.append({
            "saat": f"{saat:02d}:00", "giris": giris, "cikis": cikis, "x": x, "cubuklar": cubuklar,
            "etiket": f"{saat:02d}" if sira % 2 == 0 else None, "orta": x + bant / 2,
        })

    return {
        "genislik": GENISLIK, "yukseklik": YUKSEKLIK, "sol": SOL, "sag_kenar": GENISLIK - SAG, "taban": taban,
        "ust": UST, "bant": bant,
        "kilavuzlar": [{"y": y_konumu(d), "deger": d} for d in range(0, ust_sinir + 1, adim)],
        "gruplar": gruplar,
        "zirveler": list(zirveler.values()),
        "tablo": [g for g in gruplar if g["giris"] or g["cikis"]],
        "toplam_giris": sum(d[0] for d in sayilar.values()),
        "toplam_cikis": sum(d[1] for d in sayilar.values()),
    }
