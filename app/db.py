"""SQLite baglantisi ve Turkce metin kurallari."""

import sqlite3
from datetime import date, datetime

ALFABE = "abcçdefgğhıijklmnoöpqrsştuüvwxyz"
_HARF_SIRASI = {harf: 1000 + sira for sira, harf in enumerate(ALFABE)}


def tr_kucuk(metin):
    """Turkce kurallariyla kucuk harfe cevirir (I -> ı, İ -> i)."""
    if metin is None:
        return None
    return metin.replace("I", "ı").replace("İ", "i").lower()


def tr_anahtar(metin):
    """Turkce alfabe sirasina gore siralama anahtari uretir."""
    return [_HARF_SIRASI.get(k, ord(k) if ord(k) < 128 else 2000 + ord(k)) for k in tr_kucuk(metin)]


def _tr_karsilastir(a, b):
    ka, kb = tr_anahtar(a), tr_anahtar(b)
    return (ka > kb) - (ka < kb)


# SQLite tarihleri metin saklar; bu cift Python tarih tipleriyle gidip gelmeyi saglar.
sqlite3.register_adapter(datetime, lambda d: d.strftime("%Y-%m-%d %H:%M:%S"))
sqlite3.register_adapter(date, lambda d: d.isoformat())
sqlite3.register_converter("DATETIME", lambda b: datetime.fromisoformat(b.decode()))


class Satir(sqlite3.Row):
    """Kolonlara satir.ad seklinde erisim saglar."""

    def __getattr__(self, ad):
        try:
            return self[ad]
        except IndexError:
            raise AttributeError(ad) from None


class Imlec(sqlite3.Cursor):
    def fetchval(self):
        """Ilk satirin ilk degerini dondurur."""
        satirlar = self.fetchall()  # RETURNING sorgularinda commit oncesi hepsi okunmali
        return satirlar[0][0] if satirlar else None


class Baglanti(sqlite3.Connection):
    def execute(self, sql, *parametreler):
        """Parametreler tek tek ya da liste olarak verilebilir."""
        if len(parametreler) == 1 and isinstance(parametreler[0], (list, tuple)):
            parametreler = parametreler[0]
        return self.cursor(Imlec).execute(sql, parametreler)


def baglan(yol):
    yol.parent.mkdir(parents=True, exist_ok=True)
    cn = sqlite3.connect(
        yol, timeout=10, factory=Baglanti,
        detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
    )
    cn.row_factory = Satir
    cn.create_collation("TR", _tr_karsilastir)
    cn.create_function("tr_kucuk", 1, tr_kucuk, deterministic=True)
    cn.execute("PRAGMA foreign_keys = ON")  # SQLite'ta yabanci anahtar denetimi varsayilan olarak kapali
    cn.execute("PRAGMA journal_mode = WAL").fetchall()  # senkron yazarken sayfalar okuyabilsin
    return cn
