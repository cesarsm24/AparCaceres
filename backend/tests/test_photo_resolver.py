"""Tests del resolutor de URLs de foto.

Cubre:
- `extract_photo_url`: parser regex sobre HTML representativo de las dos
  variantes de ficha (`fichatoponimia.php` y `fichacalle.php`), HTML sin foto,
  HTML malformado y entrada vacía.
- `resolve_many`: integración con un `httpx` falsificado vía
  `httpx.MockTransport`, comprobando que respeta caché Redis (HIT positivo,
  HIT negativo, MISS) y que persiste el resultado para futuras runs.

No tocamos red real: `MockTransport` intercepta las peticiones HTTP del
cliente async dentro del propio test.
"""

from __future__ import annotations

import asyncio

import httpx

from app.infra.redis.photo_resolver import (
    _CACHE_NEGATIVE_SENTINEL,
    extract_photo_url,
    resolve_many,
)

# ============================================================
# Fixtures HTML
# ============================================================

# Snippet representativo de una ficha de toponimia (`fichatoponimia.php`)
# del SIG. La foto cuelga de `/fotosOriginales/TOPONIMIA/...`.
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


# Snippet representativo de una ficha de calle (`fichacalle.php`) — la foto
# cuelga de `/fotosOriginales/CALLES/...` con un sufijo en el nombre.
_FICHA_CALLE_CON_FOTO = """
<html><body>
  <img src="/imagenes/iconos/lupa.png">
  <img src="/fotosOriginales/CALLES/00123_a.JPG">
  <p>Calle Mayor</p>
</body></html>
"""


# Ficha que no tiene foto del lugar — solo iconos auxiliares. El extractor
# debe devolver `None`.
_FICHA_SIN_FOTO = """
<html><body>
  <img src="/imagenes/sinfoto.gif" alt="sin foto">
  <p>Aparcamiento sin imagen disponible</p>
</body></html>
"""


# HTML deliberadamente roto: etiqueta sin cerrar y atributos con comillas
# simples. El regex debe seguir encontrando la primera `<img>` válida que
# apunte a `/fotosOriginales/`, aunque venga con comillas simples.
_FICHA_MALFORMADA = """
<html><body><img src='/fotosOriginales/TOPONIMIA/no_match.jpg'>
<img src="/fotosOriginales/TOPONIMIA/buena.png" </body>
"""


# Algunas fichas del SIG ponen la foto en `href` en lugar de `src`, con URL
# absoluta. El extractor debe verla igualmente.
_FICHA_CON_HREF_ABSOLUTO = """
<html><body>
  <a href="https://sig.caceres.es/fotosOriginales/PARKING_MOTOS/3497_1.JPG">
    <img src="" alt="Foto">
  </a>
</body></html>
"""


# Otras fichas serializan la URL con barras invertidas. Hay que normalizarlas
# antes de validar la extensión y el host.
_FICHA_CON_BACKSLASHES = r"""
<html><body>
  <img src="https:\\sig.caceres.es\fotosOriginales\MOVILIDAD\4143_2_1.JPG">
</body></html>
"""


# ============================================================
# extract_photo_url: parser puro
# ============================================================

def test_extract_photo_url_toponimia():
    url = extract_photo_url(_FICHA_TOPONIMIA_CON_FOTO)
    assert url == (
        "https://sig.caceres.es/fotosOriginales/TOPONIMIA/escuela_politecnica.jpg"
    )


def test_extract_photo_url_calle_case_insensitive():
    # `.JPG` en mayúsculas debe matchear (insensible a caso).
    url = extract_photo_url(_FICHA_CALLE_CON_FOTO)
    assert url == "https://sig.caceres.es/fotosOriginales/CALLES/00123_a.JPG"


def test_extract_photo_url_sin_foto_devuelve_none():
    assert extract_photo_url(_FICHA_SIN_FOTO) is None


def test_extract_photo_url_html_vacio_devuelve_none():
    assert extract_photo_url("") is None
    assert extract_photo_url("   \n\t  ") is None


def test_extract_photo_url_soporta_comillas_simples():
    # Algunas fichas viejas usan comillas simples; también deben funcionar.
    url = extract_photo_url(_FICHA_MALFORMADA)
    assert url == "https://sig.caceres.es/fotosOriginales/TOPONIMIA/no_match.jpg"


def test_extract_photo_url_respeta_base_url_personalizada():
    url = extract_photo_url(
        _FICHA_TOPONIMIA_CON_FOTO, base_url="https://otro.host.es"
    )
    assert url.startswith("https://otro.host.es/fotosOriginales/")


def test_extract_photo_url_hace_match_en_href_absoluto():
    url = extract_photo_url(_FICHA_CON_HREF_ABSOLUTO)
    assert url == "https://sig.caceres.es/fotosOriginales/PARKING_MOTOS/3497_1.JPG"


def test_extract_photo_url_normaliza_backslashes():
    url = extract_photo_url(_FICHA_CON_BACKSLASHES)
    assert url == "https://sig.caceres.es/fotosOriginales/MOVILIDAD/4143_2_1.JPG"


# ============================================================
# resolve_many: orquestación + caché
# ============================================================

def _build_mock_client(routes: dict[str, tuple[int, str]]):
    """Devuelve un fabricante de `AsyncClient` que ruta peticiones a `routes`.

    `routes` mapea path absoluto (`/serweb/fichasig/fichatoponimia.php?mslink=1`)
    a `(status_code, body)`. El parche se aplica monkeypatcheando el
    `httpx.AsyncClient` que usa `resolve_many`.
    """
    def handler(request: httpx.Request) -> httpx.Response:
        # `resolve_many` configura el cliente con `base_url=_SIG_BASE`,
        # así que los paths llegan como path+query del request final.
        key = request.url.raw_path.decode("ascii")
        if key in routes:
            status, body = routes[key]
            return httpx.Response(status, text=body)
        return httpx.Response(404, text="not found")

    transport = httpx.MockTransport(handler)
    return transport


def test_resolve_many_resuelve_y_cachea(monkeypatch, fake_redis):
    """MISS en caché → fetch → URL persistida con la URL resuelta."""
    transport = _build_mock_client({
        "/serweb/fichasig/fichatoponimia.php?mslink=1903": (
            200, _FICHA_TOPONIMIA_CON_FOTO,
        ),
    })

    # Inyectamos el transport falso reemplazando `AsyncClient` en el módulo.
    import app.infra.redis.photo_resolver as pr
    real_client_cls = pr.httpx.AsyncClient

    def fake_client(*args, **kwargs):
        kwargs["transport"] = transport
        return real_client_cls(*args, **kwargs)

    monkeypatch.setattr(pr.httpx, "AsyncClient", fake_client)

    tasks = [
        ("aparcamientos:1903",
         "https://sig.caceres.es/serweb/fichasig/fichatoponimia.php?mslink=1903"),
    ]
    resolved = asyncio.run(resolve_many(tasks, fake_redis))

    assert resolved == {
        "aparcamientos:1903":
            "https://sig.caceres.es/fotosOriginales/TOPONIMIA/escuela_politecnica.jpg",
    }
    # Persistido positivo en caché.
    assert fake_redis.get("parking_photo:aparcamientos:1903") == (
        "https://sig.caceres.es/fotosOriginales/TOPONIMIA/escuela_politecnica.jpg"
    )


def test_resolve_many_prueba_varias_urls_hasta_encontrar_foto(monkeypatch, fake_redis):
    """Si la primera ficha no tiene foto, probamos la segunda candidata."""
    transport = _build_mock_client({
        "/serweb/fichasig/fichatoponimia.php?mslink=1": (
            200, _FICHA_SIN_FOTO,
        ),
        "/serweb/fichasig/fichacalle.php?codigo=1": (
            200, _FICHA_CALLE_CON_FOTO,
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
        "aparcamientos:1":
            "https://sig.caceres.es/fotosOriginales/CALLES/00123_a.JPG",
    }
    assert fake_redis.get("parking_photo:aparcamientos:1") == (
        "https://sig.caceres.es/fotosOriginales/CALLES/00123_a.JPG"
    )


def test_resolve_many_cache_hit_no_hace_red(monkeypatch, fake_redis):
    """Si el id ya está en caché, no se hace ninguna petición HTTP."""
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
        ("aparcamientos:7",
         "https://sig.caceres.es/serweb/fichasig/fichatoponimia.php?mslink=7"),
    ]
    resolved = asyncio.run(resolve_many(tasks, fake_redis))

    assert resolved == {
        "aparcamientos:7":
            "https://sig.caceres.es/fotosOriginales/TOPONIMIA/cached.jpg",
    }
    assert requests_made == [], "no se debería haber tocado la red en HIT"


def test_resolve_many_cache_hit_negativo_no_reintenta(monkeypatch, fake_redis):
    """Sentinel vacío en caché = "ya miramos, no hay foto". No reintentar."""
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
        ("aparcamientos:42",
         "https://sig.caceres.es/serweb/fichasig/fichatoponimia.php?mslink=42"),
    ]
    resolved = asyncio.run(resolve_many(tasks, fake_redis))

    assert resolved == {}, "el sentinel no debe filtrar URLs en el resultado"
    assert requests_made == []


def test_resolve_many_persiste_sentinel_negativo(monkeypatch, fake_redis):
    """Ficha sin foto → cacheamos el sentinel para no rescraperar siguiente run."""
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
        ("aparcamientos:99",
         "https://sig.caceres.es/serweb/fichasig/fichatoponimia.php?mslink=99"),
    ]
    resolved = asyncio.run(resolve_many(tasks, fake_redis))

    assert resolved == {}
    # El sentinel queda persistido para que un re-import lo respete.
    assert fake_redis.get("parking_photo:aparcamientos:99") == _CACHE_NEGATIVE_SENTINEL


def test_resolve_many_tolerante_a_404(monkeypatch, fake_redis):
    """Ficha 404 → tratada como "sin foto", sin abortar el batch."""
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
        ("aparcamientos:404",
         "https://sig.caceres.es/serweb/fichasig/fichatoponimia.php?mslink=404"),
    ]
    resolved = asyncio.run(resolve_many(tasks, fake_redis))

    assert resolved == {}
    assert fake_redis.get("parking_photo:aparcamientos:404") == _CACHE_NEGATIVE_SENTINEL


def test_resolve_many_filtra_pares_invalidos(fake_redis):
    """Pares con id o URL vacíos se ignoran sin tocar red ni caché."""
    tasks = [
        ("", "https://sig.caceres.es/foo"),
        ("aparcamientos:1", ""),
        (None, None),
    ]
    # No registramos ningún transport: si se intentara hacer red, fallaría.
    resolved = asyncio.run(resolve_many(tasks, fake_redis))
    assert resolved == {}
    assert fake_redis.strings == {}
