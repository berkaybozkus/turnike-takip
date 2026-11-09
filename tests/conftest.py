"""Testler gecici bir klasordeki ayri veritabanlarinda calisir; gercek veriye dokunmaz."""

import os
import tempfile
from contextlib import closing
from pathlib import Path

import pytest

_klasor = tempfile.TemporaryDirectory(prefix="turnike_test_", ignore_cleanup_errors=True)
os.environ["TAKIP_DB"] = str(Path(_klasor.name) / "turnike.db")
os.environ["KAYNAK_DB"] = str(Path(_klasor.name) / "kaynak.db")
os.environ.pop("KAYNAK_ODBC", None)


@pytest.fixture(scope="session")
def istemci():
    from app.main import app
    from app.senkron import senkronize
    from tests.yardimci import CsrfIstemci

    with CsrfIstemci(app, follow_redirects=False) as c:
        senkronize()  # arka plan dongusunu beklemeden veriyi hazirla
        assert c.post("/giris", data={"kullanici_adi": "ik", "sifre": "demo"}).status_code == 303
        yield c


@pytest.fixture
def db():
    from app import ayarlar
    from app.db import baglan

    def calistir(sql, *parametreler):
        with closing(baglan(ayarlar.TAKIP_DB)) as cn:
            imlec = cn.execute(sql, *parametreler)
            satirlar = imlec.fetchall() if imlec.description else []
            cn.commit()
            return satirlar

    return calistir
