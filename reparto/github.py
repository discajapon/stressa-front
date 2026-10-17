import requests

API = "https://api.github.com"


class GitHub:
    def __init__(self, token):
        self.s = requests.Session()
        self.s.headers.update({
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        })

    # ponytail: sin reintentos ante rate limit; el tick siguiente reintenta el día completo.
    def get(self, ruta, **params):
        r = self.s.get(API + ruta, params=params, timeout=30)
        r.raise_for_status()
        return r.json()

    def paginar(self, ruta, **params):
        r = self.s.get(API + ruta, params={"per_page": 100, **params}, timeout=30)
        while True:
            r.raise_for_status()
            yield from r.json()
            if "next" not in r.links:
                return
            r = self.s.get(r.links["next"]["url"], timeout=30)

    def texto(self, ruta, tipo, **params):
        """Contenido en texto plano (tipo "diff" o "raw"); None si GitHub no lo entrega."""
        r = self.s.get(API + ruta, params=params, headers={"Accept": f"application/vnd.github.{tipo}"}, timeout=60)
        return r.text if r.ok else None
