import re

from fastapi.testclient import TestClient


class CsrfIstemci(TestClient):
    """Gercek bir tarayici gibi POST isteklerine sayfadaki CSRF jetonunu ekler."""

    def _jeton(self):
        cevap = self.get("/giris")
        if cevap.status_code == 303:  # oturum acik
            cevap = self.get("/sifre")
        eslesme = re.search(r'name="csrf_token" value="([^"]+)"', cevap.text)
        return eslesme.group(1) if eslesme else ""

    def post(self, url, *args, data=None, **kwargs):
        veri = dict(data or {})
        veri.setdefault("csrf_token", self._jeton())
        return super().post(url, *args, data=veri, **kwargs)
