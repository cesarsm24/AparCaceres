"""Tests del resolutor de fotos municipales.

Verifican extracción de URLs desde HTML del SIG y resolución por lotes con
caché Redis, sin realizar peticiones de red reales.
"""

from __future__ import annotations

import asyncio

import httpx

from app.infra.redis.photo_resolver import (
    _CACHE_NEGATIVE_SENTINEL,
    extract_photo_url,
    resolve_many,
)

_FICHA_TOPONIMIA_CON_FOTO = """
<!DOCTYPE html>
<html>
  <head><title>Ficha</title></head>
  <body>
    <div class="cabecera"><img src="/imagenes/logo.png" alt="logo"></div>
    <h1>APARCAMIENTO ESCUELA POLITECNICA</h1>
    <table>
      <tr>
        <td>
          <img src="/fotosOriginales/TOPONIMIA/escuela_politecnica.jpg"
               alt="Foto" width="400">
        </td>
      </tr>
    </table>
  </body>
</html>
"""

_FICHA_CALLE_CON_FOTO = """
<html><body>
  <img src="/imagenes/iconos/lupa.png">
  <img src="/fotosOriginales/CALLES/00123_a.JPG">
  <p>Calle Mayor</p>
</body></html>
"""

_FICHA_SIN_FOTO = """
<html><body>
  <img src="/imagenes/sinfoto.gif" alt="sin foto">
  <p>Aparcamiento sin imagen disponible</p>
</body></html>
"""

_FICHA_MALFORMADA = """
<html><body><img src='/fotosOriginales/TOPONIMIA/no_match.jpg'>
<img src="/fotosOriginales/TOPONIMIA/buena.png" </body>
"""

_FICHA_CON_HREF_ABSOLUTO = """
<html><body>
  <a href="https://sig.caceres.es/fotosOriginales/PARKING_MOTOS/3497_1.JPG">
    <img src="" alt="Foto">
  </a>
</body></html>
"""

_FICHA_CON_BACKSLASHES = r"""
<html><body>
  <img src="https:\\sig.caceres.es\fotosOriginales\MOVILIDAD\4143_2_1.JPG">
</body></html>
"""


def test_extract_photo_url_toponimia():
    url = extract_photo_url(_FICHA_TOPONIMIA_CON_FOTO)

    assert url == (
        "https://sig.caceres.es/fotosOriginales/TOPONIMIA/escuela_politecnica.jpg"
    )


def test_extract_photo_url_calle_case_insensitive():
    url = extract_photo_url(_FICHA_CALLE_CON_FOTO)

    assert url == "https://sig.caceres.es/fotosOriginales/CALLES/00123_a.JPG"


def test_extract_photo_url_sin_foto_devuelve_none():
    assert extract_photo_url(_FICHA_SIN_FOTO) is None


def test_extract_photo_url_html_vacio_devuelve_none():
    assert extract_photo_url("") is None
    assert extract_photo_url("   \n\t  ") is None


def test_extract_photo_url_soporta_comillas_simples():
    url = extract_photo_url(_FICHA_MALFORMADA)

    assert url == "https://sig.caceres.es/fotosOriginales/TOPONIMIA/no_match.jpg"


def test_extract_photo_url_respeta_base_url_personalizada():
    url = extract_photo_url(
        _FICHA_TOPONIMIA_CON_FOTO,
        base_url="https://otro.host.es",
    )

    assert url.startswith("https://otro.host.es/fotosOriginales/")


def test_extract_photo_url_hace_match_en_href_absoluto():
    url = extract_photo_url(_FICHA_CON_HREF_ABSOLUTO)

    assert url == "https://sig.caceres.es/fotosOriginales/PARKING_MOTOS/3497_1.JPG"


def test_extract_photo_url_normaliza_backslashes():
    url = extract_photo_url(_FICHA_CON_BACKSLASHES)

    assert url == "https://sig.caceres.es/fotosOriginales/MOVILIDAD/4143_2_1.JPG"


def _build_mock_client(routes: dict[str, tuple[int, str]]):
    """Construye un transporte HTTP falso para rutas esperadas."""
    def handler(request: httpx.Request) -> httpx.Response:
        key = request.url.raw_path.decode("ascii")
        if key in routes:
            status, body = routes[key]
            return httpx.Response(status, text=body)

        return httpx.Response(404, text="not found")

    return httpx.MockTransport(handler)


def test_resolve_many_resuelve_y_cachea(monkeypatch, fake_redis):
    transport = _build_mock_client({
        "/serweb/fichasig/fichatoponimia.php?mslink=1903": (
            200,
            _FICHA_TOPONIMIA_CON_FOTO,
        ),
    })

    import app.infra.redis.photo_resolver as pr

    real_client_cls = pr.httpx.AsyncClient

    def fake_client(*args, **kwargs):
        kwargs["transport"] = transport
        return real_client_cls(*args, **kwargs)

    monkeypatch.setattr(pr.httpx, "AsyncClient", fake_client)

    tasks = [
        (
            "aparcamientos:1903",
            "https://sig.caceres.es/serweb/fichasig/fichatoponimia.php?mslink=1903",
        ),
    ]

    resolved = asyncio.run(resolve_many(tasks, fake_redis))

    assert resolved == {
        "aparcamientos:1903":
            "https://sig.caceres.es/fotosOriginales/TOPONIMIA/escuela_politecnica.jpg",
    }
    assert fake_redis.get("parking_photo:aparcamientos:1903") == (
        "https://sig.caceres.es/fotosOriginales/TOPONIMIA/escuela_politecnica.jpg"
    )


def test_resolve_many_prueba_varias_urls_hasta_encontrar_foto(monkeypatch, fake_redis):
    transport = _build_mock_client({
        "/serweb/fichasig/fichatoponimia.php?mslink=1": (
            200,
            _FICHA_SIN_FOTO,
        ),
        "/serweb/fichasig/fichacalle.php?codigo=1": (
            200,
            _FICHA_CALLE_CON_FOTO,
        ),
    })

    import app.infra.redis.photo_resolver as pr

    real_client_cls = pr.httpx.AsyncClient

    def fake_client(*args, **kwargs):
        kwargs["transport"] = transport
        return real_client_cls(*args, **kwargs)

    monkeypatch.setattr(pr.httpx, "AsyncClient", fake_client)

    tasks = [
        (
            "aparcamientos:1",
            [
                "https://sig.caceres.es/serweb/fichasig/fichatoponimia.php?mslink=1",
                "https://sig.caceres.es/serweb/fichasig/fichacalle.php?codigo=1",
            ],
        ),
    ]

    resolved = asyncio.run(resolve_many(tasks, fake_redis))

    assert resolved == {
        "aparcamientos:1": "https://sig.caceres.es/fotosOriginales/CALLES/00123_a.JPG",
    }
    assert fake_redis.get("parking_photo:aparcamientos:1") == (
        "https://sig.caceres.es/fotosOriginales/CALLES/00123_a.JPG"
    )


def test_resolve_many_cache_hit_no_hace_red(monkeypatch, fake_redis):
    fake_redis.strings["parking_photo:aparcamientos:7"] = (
        "https://sig.caceres.es/fotosOriginales/TOPONIMIA/cached.jpg"
    )
    requests_made: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests_made.append(str(request.url))
        return httpx.Response(200, text=_FICHA_TOPONIMIA_CON_FOTO)

    import app.infra.redis.photo_resolver as pr

    real_client_cls = pr.httpx.AsyncClient
    transport = httpx.MockTransport(handler)

    def fake_client(*args, **kwargs):
        kwargs["transport"] = transport
        return real_client_cls(*args, **kwargs)

    monkeypatch.setattr(pr.httpx, "AsyncClient", fake_client)

    tasks = [
        (
            "aparcamientos:7",
            "https://sig.caceres.es/serweb/fichasig/fichatoponimia.php?mslink=7",
        ),
    ]

    resolved = asyncio.run(resolve_many(tasks, fake_redis))

    assert resolved == {
        "aparcamientos:7": "https://sig.caceres.es/fotosOriginales/TOPONIMIA/cached.jpg",
    }
    assert requests_made == []


def test_resolve_many_cache_hit_negativo_no_reintenta(monkeypatch, fake_redis):
    fake_redis.strings["parking_photo:aparcamientos:42"] = _CACHE_NEGATIVE_SENTINEL
    requests_made: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests_made.append(str(request.url))
        return httpx.Response(200, text=_FICHA_TOPONIMIA_CON_FOTO)

    import app.infra.redis.photo_resolver as pr

    real_client_cls = pr.httpx.AsyncClient
    transport = httpx.MockTransport(handler)

    def fake_client(*args, **kwargs):
        kwargs["transport"] = transport
        return real_client_cls(*args, **kwargs)

    monkeypatch.setattr(pr.httpx, "AsyncClient", fake_client)

    tasks = [
        (
            "aparcamientos:42",
            "https://sig.caceres.es/serweb/fichasig/fichatoponimia.php?mslink=42",
        ),
    ]

    resolved = asyncio.run(resolve_many(tasks, fake_redis))

    assert resolved == {}
    assert requests_made == []


def test_resolve_many_persiste_sentinel_negativo(monkeypatch, fake_redis):
    transport = _build_mock_client({
        "/serweb/fichasig/fichatoponimia.php?mslink=99": (200, _FICHA_SIN_FOTO),
    })

    import app.infra.redis.photo_resolver as pr

    real_client_cls = pr.httpx.AsyncClient

    def fake_client(*args, **kwargs):
        kwargs["transport"] = transport
        return real_client_cls(*args, **kwargs)

    monkeypatch.setattr(pr.httpx, "AsyncClient", fake_client)

    tasks = [
        (
            "aparcamientos:99",
            "https://sig.caceres.es/serweb/fichasig/fichatoponimia.php?mslink=99",
        ),
    ]

    resolved = asyncio.run(resolve_many(tasks, fake_redis))

    assert resolved == {}
    assert fake_redis.get("parking_photo:aparcamientos:99") == _CACHE_NEGATIVE_SENTINEL


def test_resolve_many_tolerante_a_404(monkeypatch, fake_redis):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="not found")

    import app.infra.redis.photo_resolver as pr

    real_client_cls = pr.httpx.AsyncClient
    transport = httpx.MockTransport(handler)

    def fake_client(*args, **kwargs):
        kwargs["transport"] = transport
        return real_client_cls(*args, **kwargs)

    monkeypatch.setattr(pr.httpx, "AsyncClient", fake_client)

    tasks = [
        (
            "aparcamientos:404",
            "https://sig.caceres.es/serweb/fichasig/fichatoponimia.php?mslink=404",
        ),
    ]

    resolved = asyncio.run(resolve_many(tasks, fake_redis))

    assert resolved == {}
    assert fake_redis.get("parking_photo:aparcamientos:404") == _CACHE_NEGATIVE_SENTINEL


def test_resolve_many_filtra_pares_invalidos(fake_redis):
    tasks = [
        ("", "https://sig.caceres.es/foo"),
        ("aparcamientos:1", ""),
        (None, None),
    ]

    resolved = asyncio.run(resolve_many(tasks, fake_redis))

    assert resolved == {}
    assert fake_redis.strings == {}