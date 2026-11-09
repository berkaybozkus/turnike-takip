import re

from fastapi.testclient import TestClient as HamIstemci

from app import ayarlar
from app.guvenlik import EN_UZUN_SIFRE, GirisSiniri, sifre_dogru, sifre_ozetle
from app.main import app
from scripts import kurulum
from tests.yardimci import CsrfIstemci


def kullanici_ekle(db, ad, sifre):
    db("INSERT INTO kullanici (kullanici_adi, sifre_ozeti) VALUES (?, ?)", ad, sifre_ozetle(sifre))


def giris(c, ad, sifre):
    return c.post("/giris", data={"kullanici_adi": ad, "sifre": sifre})


def test_giris_siniri_sure_dolunca_acilir():
    an = [0]
    sinir = GirisSiniri(en_fazla=3, sure=100, saat=lambda: an[0])
    for _ in range(3):
        assert sinir.kalan_saniye("a") == 0
        sinir.hatali("a")
    assert sinir.kalan_saniye("a") > 0
    assert sinir.kalan_saniye("b") == 0
    an[0] = 101
    assert sinir.kalan_saniye("a") == 0
    assert sinir._denemeler == {}  # eski kayitlar bellekte kalmaz


def test_basarili_giris_sayaci_sifirlar():
    sinir = GirisSiniri(en_fazla=2, sure=100, saat=lambda: 0)
    sinir.hatali("a")
    sinir.sifirla("a")
    sinir.hatali("a")
    assert sinir.kalan_saniye("a") == 0


def test_cok_uzun_sifre_ozetlenmeden_reddedilir():
    assert sifre_dogru("x" * (EN_UZUN_SIFRE + 1), sifre_ozetle("demo")) is False


def test_bes_hatali_giristen_sonra_dogru_sifre_de_engellenir(db, istemci):
    kullanici_ekle(db, "kilit1", "dogrusifre")
    with CsrfIstemci(app, follow_redirects=False) as c:
        for _ in range(5):
            assert giris(c, "KİLİT1", "yanlis").status_code == 401  # buyuk harfle yazmak sayaci atlatmaz
        cevap = giris(c, "kilit1", "dogrusifre")
        assert cevap.status_code == 429 and "Çok fazla hatalı" in cevap.text
        assert c.get("/").status_code == 303
        assert giris(c, "ik", "demo").status_code == 303  # baska hesap etkilenmez


def test_csrf_jetonu_olmadan_post_reddedilir(istemci, db):
    once = db("SELECT COUNT(*) FROM departman")[0][0]
    assert HamIstemci.post(istemci, "/departmanlar", data={"ad": "Csrf Yok"}).status_code == 403
    assert HamIstemci.post(istemci, "/departmanlar", data={"ad": "Csrf Yok", "csrf_token": "yanlis"}).status_code == 403
    assert HamIstemci.post(istemci, "/departmanlar", data={"ad": "Csrf Yok", "csrf_token": "ç"}).status_code == 403
    assert db("SELECT COUNT(*) FROM departman")[0][0] == once


def test_giris_formu_da_csrf_ister():
    with HamIstemci(app, follow_redirects=False) as c:
        assert c.post("/giris", data={"kullanici_adi": "ik", "sifre": "demo"}).status_code == 403


def test_tum_post_formlarinda_csrf_alani_var():
    formlar = 0
    for dosya in (ayarlar.KOK / "app" / "templates").glob("*.html"):
        for form in re.findall(r"<form\b.*?</form>", dosya.read_text(encoding="utf-8"), re.DOTALL):
            if 'method="post"' in form:
                formlar += 1
                assert 'name="csrf_token" value="{{ csrf }}"' in form, f"{dosya.name}: {form[:80]}"
    assert formlar >= 13


def test_sifre_degistirme(db, istemci):
    kullanici_ekle(db, "sifrekisi", "eskisifre1")
    with CsrfIstemci(app, follow_redirects=False) as c:
        assert giris(c, "sifrekisi", "eskisifre1").status_code == 303

        def degistir(mevcut, yeni, tekrar=None):
            veri = {"mevcut": mevcut, "yeni": yeni, "yeni_tekrar": yeni if tekrar is None else tekrar}
            assert c.post("/sifre", data=veri).status_code == 303
            return c.get("/sifre").text

        assert "Mevcut şifre hatalı" in degistir("yanlis", "yenisifre1")
        assert "karakter olmalıdır" in degistir("eskisifre1", "kisa")
        assert "aynı değil" in degistir("eskisifre1", "yenisifre1", "baskasifre")
        assert "Şifreniz değiştirildi" in degistir("eskisifre1", "yenisifre1")

        assert c.post("/cikis").status_code == 303
        assert giris(c, "sifrekisi", "eskisifre1").status_code == 401
        assert giris(c, "sifrekisi", "yenisifre1").status_code == 303


def test_canli_demoda_sifre_degismez_ve_giris_bilgisi_gorunur(db, istemci, monkeypatch):
    kullanici_ekle(db, "demokisi", "eskisifre1")
    monkeypatch.setattr(ayarlar, "CANLI_DEMO", True)
    with CsrfIstemci(app, follow_redirects=False) as c:
        assert "Demo girişi" in c.get("/giris").text
        giris(c, "demokisi", "eskisifre1")
        c.post("/sifre", data={"mevcut": "eskisifre1", "yeni": "yenisifre1", "yeni_tekrar": "yenisifre1"})
        assert "değiştirilemez" in c.get("/sifre").text
    ozet = db("SELECT sifre_ozeti FROM kullanici WHERE kullanici_adi = 'demokisi'")[0][0]
    assert sifre_dogru("eskisifre1", ozet)


def test_demo_sifirlama_degisiklikleri_siler_kullaniciyi_korur(istemci, db):
    db("INSERT INTO departman (ad) VALUES ('Ziyaretci Dep')")
    db("INSERT INTO personel (sicil_no, ad, soyad) VALUES ('ZZZ1', 'Ziyaretci', 'Kayit')")

    kurulum.demo_sifirla()

    assert db("SELECT COUNT(*) FROM departman WHERE ad = 'Ziyaretci Dep'")[0][0] == 0
    assert db("SELECT COUNT(*) FROM personel")[0][0] == 20
    assert db("SELECT COUNT(*) FROM gecis")[0][0] > 0
    assert db("SELECT COUNT(*) FROM kullanici WHERE kullanici_adi = 'ik'")[0][0] == 1
    assert istemci.get("/").status_code == 200
