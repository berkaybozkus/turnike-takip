"""Demo ortamini hazirlar. Uygulama her acilista cagirir; tekrar calistirmak guvenlidir.

Veritabani dosyalarini ve tablolari olusturur, bos ise kurgusal ornek veriyi yukler
ve demo kullanicisini (ik / demo) ekler.

Elle calistirma (proje klasorunden): python -m scripts.kurulum
"""

from contextlib import closing

from app import ayarlar
from app.db import baglan
from app.guvenlik import sifre_ozetle
from app.senkron import senkron_kilidi, senkronize
from scripts import demo_veri


def sema_uygula(yol, dosya_adi):
    metin = (ayarlar.KOK / "sql" / dosya_adi).read_text(encoding="utf-8")
    with closing(baglan(yol)) as cn:
        cn.executescript(metin)


def main():
    sema_uygula(ayarlar.TAKIP_DB, "sema_takip.sql")
    sema_uygula(ayarlar.KAYNAK_DB, "sema_kaynak_demo.sql")

    with closing(baglan(ayarlar.TAKIP_DB)) as takip, closing(baglan(ayarlar.KAYNAK_DB)) as kaynak:
        personel = takip.execute("SELECT COUNT(*) FROM personel").fetchval()
        okutma = kaynak.execute("SELECT COUNT(*) FROM Hareketler").fetchval()

        if not takip.execute("SELECT COUNT(*) FROM kullanici").fetchval():
            takip.execute("INSERT INTO kullanici (kullanici_adi, sifre_ozeti) VALUES (?, ?)", "ik", sifre_ozetle("demo"))
            takip.commit()
            print("Demo kullanicisi eklendi: ik / demo")

    # Harici SQL Server kaynagi kullaniliyorsa kurgusal veri yuklenmez.
    if not personel and not okutma and not ayarlar.KAYNAK_ODBC:
        demo_veri.main()


def demo_sifirla():
    """Canli demoda ziyaretcilerin degisikliklerini siler ve guncel tarihli veri yukler."""
    with senkron_kilidi:
        with closing(baglan(ayarlar.TAKIP_DB)) as takip, closing(baglan(ayarlar.KAYNAK_DB)) as kaynak:
            for tablo in ("gecis", "kart", "personel", "departman"):  # sira yabanci anahtarlar icin onemli
                takip.execute(f"DELETE FROM {tablo}")
            takip.execute("DELETE FROM sqlite_sequence WHERE name IN ('gecis', 'kart', 'personel', 'departman')")
            kaynak.execute("DELETE FROM Hareketler")
            kaynak.execute("DELETE FROM sqlite_sequence WHERE name = 'Hareketler'")
            kaynak.commit()
            takip.commit()
        demo_veri.main()
    senkronize()


if __name__ == "__main__":
    main()
