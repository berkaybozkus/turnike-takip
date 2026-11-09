"""Personel, kart ve departman yonetimi sayfalari."""

import re
import sqlite3
from datetime import datetime

from fastapi import Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app import ayarlar
from app.guvenlik import EN_UZUN_SIFRE, sifre_dogru, sifre_ozetle
from app.gunluk import ARAMA_KOSULU, MANUEL_KART, arama_deseni
from app.senkron import senkron_kilidi
from app.web import TANIMSIZ_KOSUL, korumali, mesaj_birak, sayfa, takip_baglantisi, tam_sayi

KART_DESENI = re.compile(r"[0-9A-Za-z-]{1,50}")
SICIL_DESENI = re.compile(r"[Ss]([0-9]{1,9})")


def yonlendir(adres):
    # POST sonrasi yonlendirme: sayfa yenilenince form ikinci kez gonderilmez.
    return RedirectResponse(adres, status_code=303)


def kart_tanimla(cn, personel_id, kart_no):
    """Karti personele verir. (islenen okutma sayisi, kart daha once kullanilmis mi) dondurur."""
    # Kilit: senkron eski kart listesiyle ayni anda yazip kaydi tanimsiz birakmasin.
    with senkron_kilidi:
        once_kullanilmis = cn.execute("SELECT COUNT(*) FROM kart WHERE kart_no = ?", kart_no).fetchval() > 0
        cn.execute("INSERT INTO kart (kart_no, personel_id) VALUES (?, ?)", kart_no, personel_id)
        islenen = 0
        if not once_kullanilmis:
            islenen = cn.execute(
                "UPDATE gecis SET personel_id = ? WHERE kart_no = ? AND personel_id IS NULL", personel_id, kart_no
            ).rowcount
        cn.commit()
    return islenen, once_kullanilmis


def kart_ata(request, cn, personel_id, kart_no):
    """Girdiyi denetleyip karti tanimlar, sonucu mesaj olarak birakir."""
    kart_no = kart_no.strip()
    if not KART_DESENI.fullmatch(kart_no):
        mesaj_birak(request, "hata", "Kart numarası sadece harf, rakam ve tire içerebilir.")
        return

    kisi = cn.execute("SELECT ad, soyad FROM personel WHERE id = ? AND aktif = 1", personel_id).fetchone()
    if kisi is None:
        mesaj_birak(request, "hata", "Kart sadece aktif bir personele tanımlanabilir.")
        return

    try:
        islenen, once_kullanilmis = kart_tanimla(cn, personel_id, kart_no)
    except sqlite3.IntegrityError:
        mesaj_birak(request, "hata", f"{kart_no} numaralı kart başka bir personelde aktif.")
        return

    metin = f"{kart_no} numaralı kart {kisi.ad} {kisi.soyad} için tanımlandı."
    if once_kullanilmis:
        metin += " Bu kart daha önce başka bir kayıtta kullanıldığı için eski okutmalar aktarılmadı."
    elif islenen:
        metin += f" Geçmiş {islenen} okutma bu personele işlendi."
    mesaj_birak(request, "basari", metin)


def personel_hatasi(sicil_no, ad, soyad):
    if not sicil_no or not ad or not soyad:
        return "Sicil no, ad ve soyad zorunludur."
    if len(sicil_no) > 30 or len(ad) > 80 or len(soyad) > 80:
        return "Sicil no en fazla 30, ad ve soyad en fazla 80 karakter olabilir."
    return None


def sonraki_sicil(cn):
    """S ile baslayan sicil numaralarinin en buyugunden bir sonrakini uretir (S0021 gibi)."""
    # S12A gibi sayisal olmayan siciller desene uymaz ve atlanir.
    sayilar = [
        int(eslesme.group(1))
        for satir in cn.execute("SELECT sicil_no FROM personel").fetchall()
        if (eslesme := SICIL_DESENI.fullmatch(satir.sicil_no))
    ]
    return f"S{max(sayilar, default=0) + 1:04d}"


def departmanlari_getir(cn):
    return cn.execute("SELECT id, ad FROM departman ORDER BY ad").fetchall()


@korumali.get("/personel", response_class=HTMLResponse)
def personel_listesi(request: Request, ara: str = "", departman: str = "", durum: str = "aktif"):
    ara = ara.strip()[:100]
    departman_id = tam_sayi(departman)
    sorgu = """
        SELECT p.id, p.sicil_no, p.ad, p.soyad, p.aktif, d.ad AS departman,
               (SELECT group_concat(k.kart_no, ', ') FROM kart k WHERE k.personel_id = p.id AND k.aktif = 1) AS kartlar
        FROM personel p
        LEFT JOIN departman d ON d.id = p.departman_id
        WHERE 1 = 1
    """
    parametreler = []
    if durum in ("aktif", "pasif"):
        sorgu += " AND p.aktif = ?"
        parametreler.append(1 if durum == "aktif" else 0)
    if departman_id is not None:
        sorgu += " AND p.departman_id = ?"
        parametreler.append(departman_id)
    if ara:
        desen = arama_deseni(ara)
        sorgu += ARAMA_KOSULU
        parametreler += [desen, desen]
    sorgu += " ORDER BY p.ad, p.soyad, p.id"

    with takip_baglantisi() as cn:
        personeller = cn.execute(sorgu, parametreler).fetchall()
        departmanlar = departmanlari_getir(cn)

    return sayfa(request, "personel.html", {
        "personeller": personeller, "departmanlar": departmanlar,
        "ara": ara, "departman_id": departman_id, "durum": durum,
    })


@korumali.post("/personel")
def personel_ekle(request: Request, sicil_no: str = Form(""), ad: str = Form(""), soyad: str = Form(""), departman: str = Form("")):
    sicil_no, ad, soyad = sicil_no.strip(), ad.strip(), soyad.strip()

    with takip_baglantisi() as cn:
        sicil_no = sicil_no or sonraki_sicil(cn)
        hata = personel_hatasi(sicil_no, ad, soyad)
        if hata:
            mesaj_birak(request, "hata", hata)
            return yonlendir("/personel")

        try:
            yeni_id = cn.execute(
                "INSERT INTO personel (sicil_no, ad, soyad, departman_id) VALUES (?, ?, ?, ?) RETURNING id",
                sicil_no, ad, soyad, tam_sayi(departman),
            ).fetchval()
            cn.commit()
        except sqlite3.IntegrityError:
            mesaj_birak(request, "hata", f"{sicil_no} sicil numarası zaten kayıtlı ya da departman bulunamadı.")
            return yonlendir("/personel")

    mesaj_birak(request, "basari", f"{ad} {soyad} eklendi (sicil no: {sicil_no}). Şimdi kartını tanımlayabilirsiniz.")
    return yonlendir(f"/personel/{yeni_id}")


@korumali.get("/personel/{personel_id:int}", response_class=HTMLResponse)
def personel_detay(request: Request, personel_id: int):
    with takip_baglantisi() as cn:
        kisi = cn.execute("SELECT * FROM personel WHERE id = ?", personel_id).fetchone()
        if kisi is None:
            raise HTTPException(404, "Personel bulunamadı")
        kartlar = cn.execute(
            "SELECT id, kart_no, aktif FROM kart WHERE personel_id = ? ORDER BY aktif DESC, id DESC", personel_id
        ).fetchall()
        departmanlar = departmanlari_getir(cn)
    return sayfa(request, "personel_detay.html", {"kisi": kisi, "kartlar": kartlar, "departmanlar": departmanlar})


@korumali.post("/personel/{personel_id:int}/guncelle")
def personel_guncelle(request: Request, personel_id: int, sicil_no: str = Form(""), ad: str = Form(""), soyad: str = Form(""), departman: str = Form("")):
    sicil_no, ad, soyad = sicil_no.strip(), ad.strip(), soyad.strip()
    hata = personel_hatasi(sicil_no, ad, soyad)
    if hata:
        mesaj_birak(request, "hata", hata)
        return yonlendir(f"/personel/{personel_id}")

    with takip_baglantisi() as cn:
        try:
            cn.execute(
                "UPDATE personel SET sicil_no = ?, ad = ?, soyad = ?, departman_id = ? WHERE id = ?",
                sicil_no, ad, soyad, tam_sayi(departman), personel_id,
            )
            cn.commit()
        except sqlite3.IntegrityError:
            mesaj_birak(request, "hata", f"{sicil_no} sicil numarası başka bir personelde kayıtlı ya da departman bulunamadı.")
            return yonlendir(f"/personel/{personel_id}")

    mesaj_birak(request, "basari", "Bilgiler güncellendi.")
    return yonlendir(f"/personel/{personel_id}")


@korumali.post("/personel/{personel_id:int}/durum")
def personel_durum(request: Request, personel_id: int, aktif: str = Form("0")):
    aktif_mi = aktif == "1"
    with takip_baglantisi() as cn:
        cn.execute("UPDATE personel SET aktif = ? WHERE id = ?", int(aktif_mi), personel_id)
        if not aktif_mi:
            # Ayrilan kisinin karti bosa cikar; sonraki okutmalari tanimsiz olarak gorunur.
            cn.execute("UPDATE kart SET aktif = 0 WHERE personel_id = ?", personel_id)
        cn.commit()

    if aktif_mi:
        mesaj_birak(request, "basari", "Personel yeniden aktif. Yeni kartını tanımlamayı unutmayın.")
    else:
        mesaj_birak(request, "basari", "Personel pasife alındı ve kartları kapatıldı. Geçmiş kayıtları korunuyor.")
    return yonlendir(f"/personel/{personel_id}")


@korumali.post("/personel/{personel_id:int}/kart")
def personel_kart_ekle(request: Request, personel_id: int, kart_no: str = Form("")):
    with takip_baglantisi() as cn:
        kart_ata(request, cn, personel_id, kart_no)
    return yonlendir(f"/personel/{personel_id}")


@korumali.post("/kart/{kart_id:int}/kapat")
def kart_kapat(request: Request, kart_id: int):
    with takip_baglantisi() as cn:
        personel_id = cn.execute("UPDATE kart SET aktif = 0 WHERE id = ? RETURNING personel_id", kart_id).fetchval()
        cn.commit()
    if personel_id is None:
        raise HTTPException(404, "Kart bulunamadı")
    mesaj_birak(request, "basari", "Kart kapatıldı.")
    return yonlendir(f"/personel/{personel_id}")


@korumali.get("/kartlar", response_class=HTMLResponse)
def tanimsiz_kartlar(request: Request):
    with takip_baglantisi() as cn:
        kartlar = cn.execute(f"""
            SELECT g.kart_no, COUNT(*) AS okutma, MIN(g.zaman) AS "ilk [DATETIME]", MAX(g.zaman) AS "son [DATETIME]",
                   CASE WHEN EXISTS (SELECT 1 FROM kart k WHERE k.kart_no = g.kart_no) THEN 1 ELSE 0 END AS eski_kart
            FROM gecis g
            WHERE {TANIMSIZ_KOSUL}
            GROUP BY g.kart_no
            ORDER BY MAX(g.zaman) DESC
        """).fetchall()
        personeller = cn.execute("SELECT id, sicil_no, ad, soyad FROM personel WHERE aktif = 1 ORDER BY ad, soyad").fetchall()
    return sayfa(request, "kartlar.html", {"kartlar": kartlar, "personeller": personeller})


@korumali.post("/kartlar/tanimla")
def tanimsiz_kart_ata(request: Request, kart_no: str = Form(""), personel: str = Form("")):
    personel_id = tam_sayi(personel)
    if personel_id is None:
        mesaj_birak(request, "hata", "Lütfen bir personel seçin.")
        return yonlendir("/kartlar")
    with takip_baglantisi() as cn:
        kart_ata(request, cn, personel_id, kart_no)
    return yonlendir("/kartlar")


EN_KISA_SIFRE = 8


@korumali.get("/sifre", response_class=HTMLResponse)
def sifre_formu(request: Request):
    return sayfa(request, "sifre.html", {"en_kisa": EN_KISA_SIFRE, "en_uzun": EN_UZUN_SIFRE})


@korumali.post("/sifre")
def sifre_degistir(request: Request, mevcut: str = Form(""), yeni: str = Form(""), yeni_tekrar: str = Form("")):
    if ayarlar.CANLI_DEMO:
        mesaj_birak(request, "hata", "Canlı demoda şifre değiştirilemez.")
        return yonlendir("/sifre")
    if not EN_KISA_SIFRE <= len(yeni) <= EN_UZUN_SIFRE:
        mesaj_birak(request, "hata", f"Yeni şifre {EN_KISA_SIFRE}-{EN_UZUN_SIFRE} karakter olmalıdır.")
        return yonlendir("/sifre")
    if yeni != yeni_tekrar:
        mesaj_birak(request, "hata", "Yeni şifreler birbiriyle aynı değil.")
        return yonlendir("/sifre")

    kullanici = request.session["kullanici"]
    with takip_baglantisi() as cn:
        kayitli = cn.execute("SELECT sifre_ozeti FROM kullanici WHERE kullanici_adi = ? AND aktif = 1", kullanici).fetchval()
        if not sifre_dogru(mevcut, kayitli):
            mesaj_birak(request, "hata", "Mevcut şifre hatalı.")
            return yonlendir("/sifre")
        cn.execute("UPDATE kullanici SET sifre_ozeti = ? WHERE kullanici_adi = ?", sifre_ozetle(yeni), kullanici)
        cn.commit()

    mesaj_birak(request, "basari", "Şifreniz değiştirildi.")
    return yonlendir("/sifre")


@korumali.post("/manuel")
def manuel_kayit_ekle(request: Request, personel: str = Form(""), tarih: str = Form(""), saat: str = Form(""), yon: str = Form("")):
    try:
        zaman = datetime.strptime(f"{tarih} {saat}", "%Y-%m-%d %H:%M")
    except ValueError:
        mesaj_birak(request, "hata", "Lütfen geçerli bir tarih ve saat girin.")
        return yonlendir("/")

    geri = f"/?tarih={zaman.date().isoformat()}"
    personel_id = tam_sayi(personel)
    if personel_id is None or yon not in ("G", "C"):
        mesaj_birak(request, "hata", "Lütfen personel ve hareket türünü seçin.")
        return yonlendir(geri)
    if zaman > datetime.now() or zaman.year < 2000:
        mesaj_birak(request, "hata", "Gelecek bir zamana kayıt eklenemez.")
        return yonlendir("/")

    with takip_baglantisi() as cn:
        kisi = cn.execute("SELECT ad, soyad FROM personel WHERE id = ? AND aktif = 1", personel_id).fetchone()
        if kisi is None:
            mesaj_birak(request, "hata", "Kayıt sadece aktif bir personele eklenebilir.")
            return yonlendir(geri)

        # Numara negatif verilir: turnikeden gelen kayitlarla cakismaz, senkronu etkilemez.
        with senkron_kilidi:
            kaynak_id = cn.execute("SELECT MIN(COALESCE(MIN(kaynak_id), 0), 0) - 1 FROM gecis").fetchval()
            cn.execute(
                "INSERT INTO gecis (kaynak_id, kart_no, personel_id, zaman, yon, cihaz) VALUES (?, ?, ?, ?, ?, ?)",
                kaynak_id, MANUEL_KART, personel_id, zaman, yon, f"Manuel kayıt ({request.session['kullanici']})",
            )
            cn.commit()

    tur = "giriş" if yon == "G" else "çıkış"
    mesaj_birak(request, "basari", f"{kisi.ad} {kisi.soyad} için {saat} {tur} kaydı eklendi.")
    return yonlendir(geri)


@korumali.post("/manuel/{kayit_id:int}/sil")
def manuel_kayit_sil(request: Request, kayit_id: int):
    with takip_baglantisi() as cn:
        # Kosul turnikeden gelen kayitlarin bu yolla silinmesini engeller.
        gun = cn.execute(
            "DELETE FROM gecis WHERE id = ? AND kaynak_id < 0 AND kart_no = ? RETURNING date(zaman)", kayit_id, MANUEL_KART
        ).fetchval()
        cn.commit()
    if gun is None:
        raise HTTPException(404, "Manuel kayıt bulunamadı")
    mesaj_birak(request, "basari", "Manuel kayıt silindi.")
    return yonlendir(f"/?tarih={gun}")


@korumali.get("/departmanlar", response_class=HTMLResponse)
def departman_listesi(request: Request):
    with takip_baglantisi() as cn:
        departmanlar = cn.execute("""
            SELECT d.id, d.ad, (SELECT COUNT(*) FROM personel p WHERE p.departman_id = d.id) AS personel
            FROM departman d ORDER BY d.ad
        """).fetchall()
    return sayfa(request, "departmanlar.html", {"departmanlar": departmanlar})


def departman_adi_hatasi(ad):
    if not ad or len(ad) > 100:
        return "Departman adı 1-100 karakter olmalıdır."
    return None


@korumali.post("/departmanlar")
def departman_ekle(request: Request, ad: str = Form("")):
    ad = ad.strip()
    hata = departman_adi_hatasi(ad)
    if hata:
        mesaj_birak(request, "hata", hata)
        return yonlendir("/departmanlar")
    with takip_baglantisi() as cn:
        try:
            cn.execute("INSERT INTO departman (ad) VALUES (?)", ad)
            cn.commit()
            mesaj_birak(request, "basari", f"{ad} eklendi.")
        except sqlite3.IntegrityError:
            mesaj_birak(request, "hata", f"{ad} zaten var.")
    return yonlendir("/departmanlar")


@korumali.post("/departmanlar/{departman_id:int}/guncelle")
def departman_guncelle(request: Request, departman_id: int, ad: str = Form("")):
    ad = ad.strip()
    hata = departman_adi_hatasi(ad)
    if hata:
        mesaj_birak(request, "hata", hata)
        return yonlendir("/departmanlar")
    with takip_baglantisi() as cn:
        try:
            cn.execute("UPDATE departman SET ad = ? WHERE id = ?", ad, departman_id)
            cn.commit()
            mesaj_birak(request, "basari", "Departman adı güncellendi.")
        except sqlite3.IntegrityError:
            mesaj_birak(request, "hata", f"{ad} zaten var.")
    return yonlendir("/departmanlar")


@korumali.post("/departmanlar/{departman_id:int}/sil")
def departman_sil(request: Request, departman_id: int):
    with takip_baglantisi() as cn:
        try:
            cn.execute("DELETE FROM departman WHERE id = ?", departman_id)
            cn.commit()
            mesaj_birak(request, "basari", "Departman silindi.")
        except sqlite3.IntegrityError:
            mesaj_birak(request, "hata", "Bu departmanda kayıtlı personel olduğu için silinemez.")
    return yonlendir("/departmanlar")
