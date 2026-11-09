"""Sifre ozetleme, dogrulama ve giris denemesi siniri."""

import hashlib
import hmac
import os
import threading
import time

EN_UZUN_SIFRE = 128  # cok uzun metinlerle scrypt'i yormayi engeller


def _ozet(sifre, tuz):
    return hashlib.scrypt(sifre.encode("utf-8"), salt=tuz, n=2**14, r=8, p=1, dklen=32)


def sifre_ozetle(sifre):
    """Veritabanina yazilacak 'tuz$ozet' metnini uretir."""
    tuz = os.urandom(16)
    return f"{tuz.hex()}${_ozet(sifre, tuz).hex()}"


class GirisSiniri:
    """Ayni IP ve kullanici adiyla ardisik hatali girisleri bir sure engeller."""

    def __init__(self, en_fazla=5, sure=900, saat=time.monotonic):
        self.en_fazla = en_fazla
        self.sure = sure
        self.saat = saat
        self._denemeler = {}
        self._kilit = threading.Lock()

    def _temizle(self, simdi):
        # Bellek sismesin: suresi gecen kayitlar her islemde atilir.
        for anahtar, zamanlar in list(self._denemeler.items()):
            kalan = [z for z in zamanlar if simdi - z < self.sure]
            if kalan:
                self._denemeler[anahtar] = kalan
            else:
                del self._denemeler[anahtar]

    def kalan_saniye(self, anahtar):
        """Engelliyse kalan sureyi, degilse 0 dondurur."""
        with self._kilit:
            simdi = self.saat()
            self._temizle(simdi)
            zamanlar = self._denemeler.get(anahtar, [])
            if len(zamanlar) < self.en_fazla:
                return 0
            return int(self.sure - (simdi - zamanlar[0])) + 1

    def hatali(self, anahtar):
        with self._kilit:
            self._denemeler.setdefault(anahtar, []).append(self.saat())

    def sifirla(self, anahtar):
        with self._kilit:
            self._denemeler.pop(anahtar, None)


def sifre_dogru(sifre, kayitli):
    if len(sifre) > EN_UZUN_SIFRE:
        return False
    if kayitli is None:
        # Kullanici yoksa da ayni isi yap: cevap suresi kullanicinin varligini ele vermesin.
        _ozet(sifre, b"\0" * 16)
        return False
    tuz, ozet = kayitli.split("$")
    return hmac.compare_digest(_ozet(sifre, bytes.fromhex(tuz)).hex(), ozet)