-- Takip veritabaninin tablolari (SQLite). Tekrar calistirmak guvenlidir.
-- COLLATE TR: app/db.py icinde tanimli Turkce siralama ve buyuk/kucuk harf kurali.

CREATE TABLE IF NOT EXISTS departman (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ad TEXT NOT NULL COLLATE TR UNIQUE
);

CREATE TABLE IF NOT EXISTS personel (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    sicil_no     TEXT NOT NULL COLLATE TR UNIQUE,
    ad           TEXT NOT NULL COLLATE TR,
    soyad        TEXT NOT NULL COLLATE TR,
    departman_id INTEGER NULL REFERENCES departman(id),
    -- Ayrilan personel silinmez, aktif = 0 yapilir; gecmis kayitlari korunur.
    aktif        INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS kart (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    kart_no     TEXT NOT NULL,
    personel_id INTEGER NOT NULL REFERENCES personel(id),
    aktif       INTEGER NOT NULL DEFAULT 1
);

-- Bir kart ayni anda tek kiside aktif olabilir. Pasif kart baska birine verilebilir,
-- bu yuzden normal UNIQUE yerine sadece aktif kartlara bakan filtreli index kullanilir.
CREATE UNIQUE INDEX IF NOT EXISTS ux_kart_aktif_kart_no ON kart(kart_no) WHERE aktif = 1;
CREATE INDEX IF NOT EXISTS ix_kart_personel ON kart(personel_id);

CREATE TABLE IF NOT EXISTS gecis (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    -- Kaynak veritabanindaki kaydin numarasi; ayni kayit iki kez yazilamaz.
    kaynak_id   INTEGER NOT NULL UNIQUE,
    kart_no     TEXT NOT NULL,
    -- NULL ise kart henuz tanimli degildir.
    personel_id INTEGER NULL REFERENCES personel(id),
    zaman       DATETIME NOT NULL,
    -- G: giris, C: cikis, NULL: kaynak yon bilgisi vermedi.
    yon         TEXT NULL CHECK (yon IN ('G', 'C')),
    cihaz       TEXT NULL
);

-- Panele giris yapan IK kullanicilari. Sifrenin kendisi degil, ozeti saklanir.
CREATE TABLE IF NOT EXISTS kullanici (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    kullanici_adi TEXT NOT NULL COLLATE TR UNIQUE,
    sifre_ozeti   TEXT NOT NULL,
    aktif         INTEGER NOT NULL DEFAULT 1
);

-- Gunluk liste ve raporlar tarih araligina gore sorgulanir.
CREATE INDEX IF NOT EXISTS ix_gecis_zaman ON gecis(zaman);
CREATE INDEX IF NOT EXISTS ix_gecis_personel_zaman ON gecis(personel_id, zaman);

-- Tanimsiz kartlari hizli bulmak icin.
CREATE INDEX IF NOT EXISTS ix_gecis_tanimsiz_kart ON gecis(kart_no) WHERE personel_id IS NULL;
