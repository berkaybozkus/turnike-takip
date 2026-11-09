"""Uygulama ayarlari. Varsayilanlar yerel demo icindir; .env dosyasi bunlari ezer."""

import os
import secrets
from pathlib import Path

from dotenv import load_dotenv

KOK = Path(__file__).resolve().parent.parent
load_dotenv(KOK / ".env")

TAKIP_DB = Path(os.getenv("TAKIP_DB", KOK / "data" / "turnike.db"))
KAYNAK_DB = Path(os.getenv("KAYNAK_DB", KOK / "data" / "kaynak_demo.db"))

# Dolu ise okutmalar demo dosyasi yerine bu SQL Server'dan okunur (pyodbc kurulu olmali).
KAYNAK_ODBC = os.getenv("KAYNAK_ODBC")

SENKRON_ARALIGI = int(os.getenv("SENKRON_ARALIGI", "30"))  # saniye

# Internette herkese acik demo: veri duzenli sifirlanir, sifre degistirilemez, cerez sadece HTTPS.
CANLI_DEMO = os.getenv("CANLI_DEMO", "") == "1"
DEMO_SIFIRLAMA_DAKIKA = int(os.getenv("DEMO_SIFIRLAMA_DAKIKA", "60"))

# Oturum cerezini imzalar. .env'de yoksa her baslatmada yenisi uretilir (herkes yeniden giris yapar).
OTURUM_ANAHTARI = os.getenv("OTURUM_ANAHTARI") or secrets.token_urlsafe(32)
