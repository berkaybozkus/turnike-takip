-- Turnike yaziliminin kayit tuttugu veritabanini taklit eden demo tablosu (SQLite).

CREATE TABLE IF NOT EXISTS Hareketler (
    HareketId  INTEGER PRIMARY KEY AUTOINCREMENT,
    KartNo     TEXT NOT NULL,
    OlayZamani DATETIME NOT NULL,
    Yon        TEXT NULL,
    CihazAdi   TEXT NULL
);
