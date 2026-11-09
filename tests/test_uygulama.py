"""Uygulamayi gecici, kurgusal veriyle bastan sona dener."""

import re
from datetime import date, datetime, timedelta
from io import BytesIO

from openpyxl import load_workbook

from app.main import app
from app.senkron import senkronize
from tests.yardimci import CsrfIstemci as TestClient


def gonder(c, adres, **veri):
    cevap = c.post(adres, data=veri)
    assert cevap.status_code == 303, cevap.text[:300]
    return cevap.headers["location"], c.get(cevap.headers["location"]).text


def okutmali_gun(db):
    return db("SELECT date(MIN(zaman)) FROM gecis WHERE personel_id IS NOT NULL")[0][0]


def excel_satirlari(cevap):
    return list(load_workbook(BytesIO(cevap.content)).active.iter_rows(min_row=2, values_only=True))


def personel_ekle(c, sicil, ad="Test", soyad="Kişi"):
    yer, _ = gonder(c, "/personel", sicil_no=sicil, ad=ad, soyad=soyad, departman="")
    return int(yer.rsplit("/", 1)[1])


def test_oturumsuz_sayfalar_girise_yonlenir():
    with TestClient(app, follow_redirects=False) as c:
        for adres in ("/", "/rapor", "/rapor/excel", "/personel", "/kartlar", "/departmanlar"):
            assert c.get(adres).headers["location"] == "/giris"
        assert c.post("/personel", data={"sicil_no": "X", "ad": "a", "soyad": "b"}).headers["location"] == "/giris"


def test_yanlis_sifre_reddedilir():
    with TestClient(app, follow_redirects=False) as c:
        cevap = c.post("/giris", data={"kullanici_adi": "ik", "sifre": "yanlis"})
        assert cevap.status_code == 401 and "hatalı" in cevap.text
        assert c.post("/giris", data={"kullanici_adi": "yok", "sifre": "demo"}).status_code == 401
        assert c.get("/").status_code == 303


def test_senkron_kayitlari_tekrar_yazmaz(db, istemci):
    once = db("SELECT COUNT(*) FROM gecis")[0][0]
    assert once > 0
    assert senkronize() == 0
    assert db("SELECT COUNT(*) FROM gecis")[0][0] == once


def test_gunluk_liste_ve_filtreler(istemci, db):
    gun = okutmali_gun(db)
    metin = istemci.get(f"/?tarih={gun}").text
    assert metin.count('<tbody class=') >= 20
    assert "Ayşe Yılmaz" in metin

    assert "İbrahim Aslan" in istemci.get(f"/?tarih={gun}&ara=ibrahim").text
    assert "Hatice Kılıç" in istemci.get(f"/?tarih={gun}&ara=KILIÇ").text
    assert "Bu filtrelere uyan" in istemci.get(f"/?tarih={gun}&ara=%25").text

    departman = db("SELECT id FROM departman WHERE ad = 'İnsan Kaynakları'")[0][0]
    assert istemci.get(f"/?tarih={gun}&departman={departman}").text.count('<tbody class=') == 2


def test_gunluk_hatali_girdiler_sayfayi_dusurmez(istemci):
    for adres in ("/?tarih=bozuk", "/?departman=abc", "/?departman=99999999999999999999", "/?tarih=9999-12-31"):
        assert istemci.get(adres).status_code == 200


def test_enjeksiyon_denemeleri_etkisiz(istemci):
    assert "<script>alert(1)" not in istemci.get("/?ara=<script>alert(1)</script>").text
    assert "Bu filtrelere uyan" in istemci.get("/?ara=' OR 1=1 --").text


def test_tanimsiz_kart_tanimlaninca_gecmisi_islenir(istemci, db):
    pid = personel_ekle(istemci, "T100")
    adet = db("SELECT COUNT(*) FROM gecis WHERE kart_no = '9000000001' AND personel_id IS NULL")[0][0]
    assert adet > 0
    assert "9000000001" in istemci.get("/kartlar").text

    _, metin = gonder(istemci, "/kartlar/tanimla", kart_no="9000000001", personel=str(pid))
    assert f"Geçmiş {adet} okutma" in metin
    assert db("SELECT COUNT(*) FROM gecis WHERE kart_no = '9000000001' AND personel_id = ?", pid)[0][0] == adet
    assert "9000000001" not in istemci.get("/kartlar").text


def test_kapali_kart_yeni_sahibine_eski_okutma_aktarmaz(istemci, db):
    ilk, ikinci = personel_ekle(istemci, "T200"), personel_ekle(istemci, "T201")
    gonder(istemci, f"/personel/{ilk}/kart", kart_no="T-KART-1")

    _, metin = gonder(istemci, f"/personel/{ikinci}/kart", kart_no="T-KART-1")
    assert "başka bir personelde aktif" in metin

    kart_id = db("SELECT id FROM kart WHERE kart_no = 'T-KART-1' AND aktif = 1")[0][0]
    gonder(istemci, f"/kart/{kart_id}/kapat")
    db("INSERT INTO gecis (kaynak_id, kart_no, personel_id, zaman, yon) VALUES (-1, 'T-KART-1', NULL, ?, 'G')", datetime(2026, 1, 1, 9, 0))
    assert "Daha önce kapatılmış" in istemci.get("/kartlar").text

    _, metin = gonder(istemci, "/kartlar/tanimla", kart_no="T-KART-1", personel=str(ikinci))
    assert "eski okutmalar aktarılmadı" in metin
    assert db("SELECT COUNT(*) FROM gecis WHERE personel_id = ?", ikinci)[0][0] == 0


def test_personel_kurallari(istemci, db):
    pid = personel_ekle(istemci, "T300", ad="<b>Kaçış</b>")
    assert "<b>Kaçış</b>" not in istemci.get(f"/personel/{pid}").text

    _, metin = gonder(istemci, "/personel", sicil_no="t300", ad="A", soyad="B", departman="")
    assert "zaten kayıtlı" in metin
    _, metin = gonder(istemci, "/personel", sicil_no="", ad="", soyad="B", departman="")
    assert "zorunludur" in metin
    _, metin = gonder(istemci, f"/personel/{pid}/kart", kart_no="bad kart;")
    assert "sadece harf" in metin
    assert istemci.get("/personel/999999").status_code == 404


def test_otomatik_sicil_numarasi(istemci, db):
    gonder(istemci, "/personel", sicil_no="S9000", ad="Oto", soyad="Elle", departman="")
    gonder(istemci, "/personel", sicil_no="S12A", ad="Oto", soyad="Harfli", departman="")
    _, metin = gonder(istemci, "/personel", sicil_no="", ad="Oto", soyad="Sonra", departman="")
    assert "sicil no: S9001" in metin


def test_pasife_alinan_kisi_kartlarini_kaybeder_gecmisi_kalir(istemci, db):
    pid = personel_ekle(istemci, "T400", ad="Pasif", soyad="Deneme")
    gonder(istemci, f"/personel/{pid}/kart", kart_no="T-KART-4")
    db("INSERT INTO gecis (kaynak_id, kart_no, personel_id, zaman, yon) VALUES (-4, 'T-KART-4', ?, ?, 'G')", pid, datetime(2026, 2, 3, 9, 0))

    gonder(istemci, f"/personel/{pid}/durum", aktif="0")
    assert db("SELECT COUNT(*) FROM kart WHERE personel_id = ? AND aktif = 1", pid)[0][0] == 0
    assert "T400" not in istemci.get("/personel").text
    assert "T400" in istemci.get("/personel?durum=pasif").text
    assert "Pasif Deneme" not in istemci.get(f"/?tarih={date.today()}").text
    assert "Pasif Deneme" in istemci.get("/?tarih=2026-02-03").text
    _, metin = gonder(istemci, f"/personel/{pid}/kart", kart_no="T-KART-5")
    assert "aktif bir personele" in metin


def test_departman_kurallari(istemci, db):
    gonder(istemci, "/departmanlar", ad="Deneme Dep")
    _, metin = gonder(istemci, "/departmanlar", ad="deneme dep")
    assert "zaten var" in metin
    did = db("SELECT id FROM departman WHERE ad = 'Deneme Dep'")[0][0]

    pid = personel_ekle(istemci, "T500")
    gonder(istemci, f"/personel/{pid}/guncelle", sicil_no="T500", ad="Test", soyad="Kişi", departman=str(did))
    _, metin = gonder(istemci, f"/departmanlar/{did}/sil")
    assert "silinemez" in metin

    gonder(istemci, f"/personel/{pid}/guncelle", sicil_no="T500", ad="Test", soyad="Kişi", departman="")
    _, metin = gonder(istemci, f"/departmanlar/{did}/sil")
    assert "Departman silindi" in metin


def test_manuel_kayit_ekleme_ve_silme(istemci, db):
    pid = personel_ekle(istemci, "T600", ad="Manuel", soyad="Deneme")
    gun = (date.today() - timedelta(days=1)).isoformat()

    yer, metin = gonder(istemci, "/manuel", personel=str(pid), tarih=gun, saat="08:45", yon="G")
    assert yer == f"/?tarih={gun}"
    assert "08:45 giriş kaydı eklendi" in metin
    assert "Manuel Deneme" in metin and "Çıkış yok" in metin and "Manuel kayıt (ik)" in metin

    _, metin = gonder(istemci, "/manuel", personel=str(pid), tarih=gun, saat="17:30", yon="C")
    satirlar = db("SELECT id, kaynak_id FROM gecis WHERE personel_id = ? ORDER BY zaman", pid)
    assert len(satirlar) == 2 and all(s.kaynak_id < 0 for s in satirlar)
    assert senkronize() == 0  # manuel kayit senkronun kaldigi yeri bozmaz

    _, metin = gonder(istemci, f"/manuel/{satirlar[0].id}/sil")
    assert "Manuel kayıt silindi" in metin
    assert len(db("SELECT id FROM gecis WHERE personel_id = ?", pid)) == 1


def test_manuel_kayit_hatali_girdiler(istemci, db):
    pid = str(db("SELECT id FROM personel WHERE aktif = 1 LIMIT 1")[0][0])
    yarin = (date.today() + timedelta(days=1)).isoformat()
    bugun = date.today().isoformat()
    once = db("SELECT COUNT(*) FROM gecis")[0][0]

    assert "Gelecek bir zamana" in gonder(istemci, "/manuel", personel=pid, tarih=yarin, saat="09:00", yon="G")[1]
    assert "geçerli bir tarih" in gonder(istemci, "/manuel", personel=pid, tarih="bozuk", saat="09:00", yon="G")[1]
    assert "geçerli bir tarih" in gonder(istemci, "/manuel", personel=pid, tarih=bugun, saat="25:00", yon="G")[1]
    assert "hareket türünü" in gonder(istemci, "/manuel", personel=pid, tarih=bugun, saat="00:00", yon="X")[1]
    assert "hareket türünü" in gonder(istemci, "/manuel", personel="", tarih=bugun, saat="00:00", yon="G")[1]
    assert "aktif bir personele" in gonder(istemci, "/manuel", personel="99999", tarih=bugun, saat="00:00", yon="G")[1]
    assert db("SELECT COUNT(*) FROM gecis")[0][0] == once


def test_turnike_kaydi_manuel_silme_yoluyla_silinemez(istemci, db):
    kayit = db("SELECT id FROM gecis WHERE kaynak_id > 0 LIMIT 1")[0][0]
    assert istemci.post(f"/manuel/{kayit}/sil").status_code == 404
    assert db("SELECT COUNT(*) FROM gecis WHERE id = ?", kayit)[0][0] == 1


def test_gunluk_tasarim_parcalari_ve_sekmeler(istemci, db):
    gun = okutmali_gun(db)
    metin = istemci.get(f"/?tarih={gun}").text
    for parca in ("Günün giriş ve çıkışları", "Kayıtlı personel", "Saatlik hareket", "Son hareketler", "Manuel kayıt ekle", "Tablo olarak göster"):
        assert parca in metin
    assert f"/rapor/excel?bas={gun}&amp;bit={gun}" in metin or f"/rapor/excel?bas={gun}&bit={gun}" in metin

    kayitsiz = istemci.get("/?tarih=2020-01-01&durum=kayitsiz").text
    assert "rozet kayit-yok" in kayitsiz and "rozet tamam" not in kayitsiz
    assert "Bu gün için hareket yok" in kayitsiz
    assert istemci.get("/?durum=<script>").status_code == 200
    cikan = istemci.get(f"/?tarih={gun}&durum=cikan").text
    assert "rozet kayit-yok" not in cikan


def test_rapor_excel_tum_kisi_gunlerini_icerir(istemci, db):
    bas = okutmali_gun(db)
    bit = date.today().isoformat()
    cevap = istemci.get(f"/rapor/excel?bas={bas}&bit={bit}")
    assert cevap.status_code == 200
    assert f"turnike_raporu_{bas}_{bit}.xlsx" in cevap.headers["content-disposition"]

    satirlar = excel_satirlari(cevap)
    beklenen = db(
        "SELECT COUNT(*) FROM (SELECT DISTINCT personel_id, date(zaman) FROM gecis WHERE personel_id IS NOT NULL AND zaman >= ? AND zaman < ?)",
        bas, (date.today() + timedelta(days=1)).isoformat(),
    )[0][0]
    assert len({(s[0], s[2]) for s in satirlar}) == beklenen
    assert [s[0] for s in satirlar] == sorted(s[0] for s in satirlar)


def test_rapor_tarih_sinirlari_ve_hatalari(istemci, db):
    gun = date.fromisoformat(okutmali_gun(db))
    satirlar = excel_satirlari(istemci.get(f"/rapor/excel?bas={gun}&bit={gun}"))
    assert satirlar and {s[0].date() for s in satirlar} == {gun}

    assert "sonra olamaz" in istemci.get("/rapor?bas=2026-11-09&bit=2026-11-01").text
    assert "en fazla 366" in istemci.get("/rapor?bas=2024-01-01&bit=2026-11-01").text
    assert istemci.get("/rapor/excel?bas=bozuk&bit=2026-11-01").headers["location"] == "/rapor"
    assert "geçerli bir başlangıç" in istemci.get("/rapor").text
    assert re.search(r'id="gun-sayisi"[^>]*value="7"', istemci.get("/rapor").text)
