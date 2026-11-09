from datetime import date, datetime

import pytest

from app.db import baglan, tr_anahtar, tr_kucuk


@pytest.fixture
def cn(tmp_path):
    baglanti = baglan(tmp_path / "deneme.db")
    baglanti.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, ad TEXT COLLATE TR UNIQUE, zaman DATETIME)")
    yield baglanti
    baglanti.close()


def test_tr_kucuk_noktali_noktasiz_i():
    assert tr_kucuk("KILIÇ") == "kılıç"
    assert tr_kucuk("İbrahim") == "ibrahim"


def test_turkce_alfabe_sirasi():
    adlar = ["Zeynep", "Çetin", "Can", "Ömer", "Onur", "İbrahim", "Ilgın", "Şule", "Selin"]
    assert sorted(adlar, key=tr_anahtar) == ["Can", "Çetin", "Ilgın", "İbrahim", "Onur", "Ömer", "Selin", "Şule", "Zeynep"]


def test_unique_turkce_buyuk_kucuk_harfe_duyarsiz(cn):
    cn.execute("INSERT INTO t (ad) VALUES (?)", "İzmir")
    with pytest.raises(Exception):
        cn.execute("INSERT INTO t (ad) VALUES (?)", "izmir")
    cn.execute("INSERT INTO t (ad) VALUES (?)", "ızmir")  # noktasiz ı farkli harftir


def test_tarih_gidip_gelir_ve_aralik_karsilastirilir(cn):
    zaman = datetime(2026, 11, 6, 8, 30, 15)
    cn.execute("INSERT INTO t (ad, zaman) VALUES (?, ?)", "a", zaman)
    satir = cn.execute("SELECT zaman FROM t WHERE zaman >= ? AND zaman < ?", date(2026, 11, 6), date(2026, 11, 7)).fetchone()
    assert satir.zaman == zaman


def test_fetchval_ve_liste_parametre(cn):
    cn.execute("INSERT INTO t (ad) VALUES (?)", ["a"])
    assert cn.execute("SELECT COUNT(*) FROM t").fetchval() == 1
    assert cn.execute("SELECT id FROM t WHERE ad = ?", "yok").fetchval() is None


def test_yabanci_anahtar_acik(tmp_path):
    b = baglan(tmp_path / "fk.db")
    b.execute("CREATE TABLE a (id INTEGER PRIMARY KEY)")
    b.execute("CREATE TABLE b (a_id INTEGER REFERENCES a(id))")
    with pytest.raises(Exception):
        b.execute("INSERT INTO b VALUES (99)")
    b.close()
