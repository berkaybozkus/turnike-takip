"""IK kullanicisi olusturur; kullanici varsa sifresini yeniler.

Sifre verilmezse rastgele uretir ve bir kez ekrana yazar.
Calistirma (proje klasorunden): python -m scripts.kullanici_olustur ik [sifre]
"""

import secrets
import sys
from contextlib import closing

from app import ayarlar
from app.db import baglan
from app.guvenlik import sifre_ozetle


def main():
    if len(sys.argv) not in (2, 3):
        sys.exit("Kullanim: python -m scripts.kullanici_olustur <kullanici_adi> [sifre]")

    kullanici_adi = sys.argv[1]
    sifre = sys.argv[2] if len(sys.argv) == 3 else secrets.token_urlsafe(9)
    ozet = sifre_ozetle(sifre)

    with closing(baglan(ayarlar.TAKIP_DB)) as cn:
        guncellenen = cn.execute(
            "UPDATE kullanici SET sifre_ozeti = ?, aktif = 1 WHERE kullanici_adi = ?", ozet, kullanici_adi
        ).rowcount
        if not guncellenen:
            cn.execute("INSERT INTO kullanici (kullanici_adi, sifre_ozeti) VALUES (?, ?)", kullanici_adi, ozet)
        cn.commit()

    print(f"Kullanici: {kullanici_adi}")
    print(f"Sifre: {sifre}")


if __name__ == "__main__":
    main()
