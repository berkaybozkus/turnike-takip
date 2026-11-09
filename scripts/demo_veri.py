"""Demo icin kurgusal personel, kart ve turnike okutmalari uretir.

- Departman, personel ve kartlar takip veritabanina yazilir.
- Okutmalar, turnike sistemini taklit eden kaynak veritabanina yazilir.
  Takip veritabanindaki gecis tablosunu doldurmak senkronun isidir.

Veri varsa hicbir sey yazmadan durur. Calistirma: python -m scripts.demo_veri
Sadece okutmalari bastan uretmek icin: python -m scripts.demo_veri --okutmalari-yenile
"""

import random
import sys
from contextlib import closing
from datetime import datetime, time, timedelta

from app.ayarlar import KAYNAK_DB, TAKIP_DB
from app.db import baglan

GUN_SAYISI = 28
CIHAZLAR = ["Ana Giriş Turnike 1", "Ana Giriş Turnike 2", "Arka Kapı Turnike"]

# Isimler kurgusaldir.
PERSONEL = [
    ("Ayşe", "Yılmaz", "İnsan Kaynakları"),
    ("Mehmet", "Kaya", "İnsan Kaynakları"),
    ("Zeynep", "Demir", "Muhasebe"),
    ("Mustafa", "Çelik", "Muhasebe"),
    ("Elif", "Şahin", "Muhasebe"),
    ("Ahmet", "Yıldız", "Bilgi İşlem"),
    ("Fatma", "Öztürk", "Bilgi İşlem"),
    ("Emre", "Aydın", "Bilgi İşlem"),
    ("Merve", "Arslan", "Bilgi İşlem"),
    ("Hasan", "Doğan", "Üretim"),
    ("Hatice", "Kılıç", "Üretim"),
    ("İbrahim", "Aslan", "Üretim"),
    ("Esra", "Çetin", "Üretim"),
    ("Ömer", "Kara", "Üretim"),
    ("Selin", "Koç", "Üretim"),
    ("Burak", "Kurt", "Satış"),
    ("Gizem", "Özdemir", "Satış"),
    ("Can", "Şimşek", "Satış"),
    ("Derya", "Polat", "Satış"),
    ("Onur", "Güneş", "Satış"),
]


def gun_okutmalari(rng, kart_no, gun):
    """Bir kisinin bir gunluk okutmalarini (kart, zaman, yon, cihaz) olarak dondurur."""
    if rng.random() < 0.05:  # gelmedi
        return []

    giris = datetime.combine(gun, time(8, 30)) + timedelta(seconds=rng.randint(-1800, 1200))
    cikis = datetime.combine(gun, time(18, 30)) + timedelta(seconds=rng.randint(-900, 2700))
    cihaz = rng.choice(CIHAZLAR)
    olaylar = [(giris, "G"), (cikis, "C")]

    if rng.random() < 0.4:  # molada disari cikti
        cikti = datetime.combine(gun, time(13, 0)) + timedelta(seconds=rng.randint(-300, 600))
        dondu = datetime.combine(gun, time(14, 0)) + timedelta(seconds=rng.randint(-600, 600))
        olaylar += [(cikti, "C"), (dondu, "G")]

    olaylar.sort()

    # Gercek hayattaki hatalar: hesaplama adimi bunlari yakalayabilmeli.
    sans = rng.random()
    if sans < 0.03:  # cikista kart okutmayi unuttu
        olaylar.pop()
    elif sans < 0.04:  # giriste kart okutmayi unuttu
        olaylar.pop(0)
    elif sans < 0.07:  # ayni yonde art arda iki kez okuttu
        zaman, yon = olaylar[0]
        olaylar.insert(1, (zaman + timedelta(seconds=rng.randint(3, 25)), yon))

    return [(kart_no, zaman, yon, cihaz) for zaman, yon in olaylar]


def okutmalari_uret(rng, kartlar, simdi):
    """Son GUN_SAYISI gunun okutmalarini zaman sirasiyla dondurur."""
    okutmalar = []
    gunler = [simdi.date() - timedelta(days=i) for i in range(GUN_SAYISI)]
    for gun in gunler:
        if gun.weekday() >= 5:  # hafta sonu
            continue
        for kart_no in kartlar:
            okutmalar += gun_okutmalari(rng, kart_no, gun)

    # Sisteme tanimli olmayan kartlar (ziyaretci, yeni personel vb.).
    for kart_no in ("9000000001", "9000000002"):
        for gun in rng.sample(gunler, 5):
            giris = datetime.combine(gun, time(10, 0)) + timedelta(seconds=rng.randint(0, 3600))
            okutmalar.append((kart_no, giris, "G", CIHAZLAR[0]))
            okutmalar.append((kart_no, giris + timedelta(minutes=rng.randint(30, 120)), "C", CIHAZLAR[0]))

    # Gercek bir turnike gibi: gelecek zamanli kayit yok, numaralar zamanla artar.
    return sorted((o for o in okutmalar if o[1] <= simdi), key=lambda o: o[1])


def okutmalari_yaz(kaynak, okutmalar):
    kaynak.executemany(
        "INSERT INTO Hareketler (KartNo, OlayZamani, Yon, CihazAdi) VALUES (?, ?, ?, ?)",
        okutmalar,
    )


def okutmalari_yenile():
    """Personel ve kartlara dokunmadan demo okutmalarini silip yeniden uretir."""
    rng = random.Random(2026)
    simdi = datetime.now().replace(microsecond=0)

    with closing(baglan(TAKIP_DB)) as takip, closing(baglan(KAYNAK_DB)) as kaynak:
        kartlar = [s.kart_no for s in takip.execute("SELECT kart_no FROM kart WHERE aktif = 1 ORDER BY personel_id").fetchall()]
        if not kartlar:
            sys.exit("Aktif kart yok, hicbir sey degismedi.")

        okutmalar = okutmalari_uret(rng, kartlar, simdi)
        takip.execute("DELETE FROM gecis")
        kaynak.execute("DELETE FROM Hareketler")
        kaynak.execute("DELETE FROM sqlite_sequence WHERE name = 'Hareketler'")  # numaralar 1'den baslasin
        okutmalari_yaz(kaynak, okutmalar)

        kaynak.commit()
        takip.commit()
        print(f"{len(okutmalar)} okutma yeniden uretildi; gecis tablosu temizlendi.")


def main():
    rng = random.Random(2026)
    simdi = datetime.now().replace(microsecond=0)

    with closing(baglan(TAKIP_DB)) as takip, closing(baglan(KAYNAK_DB)) as kaynak:
        dolu = takip.execute(
            "SELECT (SELECT COUNT(*) FROM departman) + (SELECT COUNT(*) FROM personel)"
        ).fetchval() + kaynak.execute("SELECT COUNT(*) FROM Hareketler").fetchval()
        if dolu:
            sys.exit("Tablolarda veri var, hicbir sey yazilmadi.")

        departmanlar = {}
        for ad in dict.fromkeys(p[2] for p in PERSONEL):
            departmanlar[ad] = takip.execute("INSERT INTO departman (ad) VALUES (?) RETURNING id", ad).fetchval()

        kartlar = []
        kullanilan = set()
        for sira, (ad, soyad, departman) in enumerate(PERSONEL, start=1):
            personel_id = takip.execute(
                "INSERT INTO personel (sicil_no, ad, soyad, departman_id) VALUES (?, ?, ?, ?) RETURNING id",
                f"S{sira:04d}", ad, soyad, departmanlar[departman],
            ).fetchval()
            while (kart_no := str(rng.randint(1_000_000_000, 4_000_000_000))) in kullanilan:
                pass
            kullanilan.add(kart_no)
            takip.execute("INSERT INTO kart (kart_no, personel_id) VALUES (?, ?)", kart_no, personel_id)
            kartlar.append(kart_no)

        okutmalar = okutmalari_uret(rng, kartlar, simdi)
        okutmalari_yaz(kaynak, okutmalar)

        kaynak.commit()
        takip.commit()
        print(f"{len(departmanlar)} departman, {len(kartlar)} personel ve kart, {len(okutmalar)} okutma yazildi.")


if __name__ == "__main__":
    if "--okutmalari-yenile" in sys.argv:
        okutmalari_yenile()
    else:
        main()
