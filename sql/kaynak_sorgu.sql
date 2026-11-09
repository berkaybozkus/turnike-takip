-- Turnike kayitlarini okuyan sorgu. Sirketin veritabanina gecince sadece bu dosya degisir.
-- Sonuc bu sirada ve bu adlarla donmeli: kaynak_id, kart_no, zaman, yon, cihaz
-- ? isareti: en son aktarilan kaynak_id degeri (kod tarafindan doldurulur).
SELECT HareketId  AS kaynak_id,
       KartNo     AS kart_no,
       OlayZamani AS zaman,
       Yon        AS yon,
       CihazAdi   AS cihaz
FROM Hareketler
WHERE HareketId > ?
ORDER BY HareketId;
