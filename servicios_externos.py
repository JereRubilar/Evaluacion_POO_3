import os
import re
from dotenv import load_dotenv
import requests
import time

load_dotenv()


class ServicioExternoError(Exception):
    """Error controlado para fallos en servicios externos o validación de entradas."""


_PATRON_CIUDAD = re.compile(r"^[a-zA-ZÀ-ÿ\s\-.]{2,80}$")
_PATRON_MONEDA = re.compile(r"^[A-Z]{3}$")
_CACHE_MONEDAS = {"expira": 0.0, "monedas": []}

_CODIGOS_CLIMA = {
    0: "Despejado",
    1: "Mayormente despejado",
    2: "Parcialmente nublado",
    3: "Nublado",
    45: "Niebla",
    48: "Niebla con escarcha",
    51: "Llovizna ligera",
    53: "Llovizna moderada",
    55: "Llovizna densa",
    61: "Lluvia ligera",
    63: "Lluvia moderada",
    65: "Lluvia fuerte",
    71: "Nevada ligera",
    73: "Nevada moderada",
    75: "Nevada fuerte",
    80: "Chubascos ligeros",
    81: "Chubascos moderados",
    82: "Chubascos fuertes",
    95: "Tormenta eléctrica",
}


def _obtener_api_key_monedas() -> str:
    api_key = os.getenv("EXCHANGERATE_API_KEY", "").strip()
    if not api_key:
        raise ServicioExternoError(
            "El servicio de tipo de cambio no está configurado correctamente en el servidor."
        )
    return api_key


def _validar_ciudad(ciudad: str) -> str:
    limpia = (ciudad or "").strip()
    if not limpia or not _PATRON_CIUDAD.match(limpia):
        raise ServicioExternoError("Ingresa un nombre de ciudad válido (solo letras y espacios).")
    return limpia


def _validar_moneda(codigo: str, etiqueta: str = "moneda") -> str:
    limpia = (codigo or "").strip().upper()
    if not _PATRON_MONEDA.match(limpia):
        raise ServicioExternoError(f"El código de {etiqueta} debe tener 3 letras (ej. CLP, USD, EUR).")
    return limpia


def _validar_monto(monto) -> float:
    try:
        if isinstance(monto, str):
            monto = monto.replace(",", ".").strip()
        valor = float(monto)
    except (TypeError, ValueError) as exc:
        raise ServicioExternoError("El monto debe ser un número válido.") from exc

    if valor <= 0:
        raise ServicioExternoError("El monto debe ser mayor que cero.")
    return valor


def _peticion_get_json(url: str, params: dict | None = None, timeout: int = 8) -> dict:
    try:
        resp = requests.get(url, params=params, timeout=timeout)
    except requests.Timeout as exc:
        raise ServicioExternoError("El servicio externo tardó demasiado en responder.") from exc
    except requests.ConnectionError as exc:
        raise ServicioExternoError("No fue posible establecer conexión con el servicio externo.") from exc
    except requests.RequestException as exc:
        raise ServicioExternoError("Error de red al consultar el servicio externo.") from exc

    if resp.status_code in (401, 403):
        raise ServicioExternoError("Error de autenticación con el proveedor externo.")
    if resp.status_code == 404:
        raise ServicioExternoError("No se encontró el recurso o moneda solicitada en el servicio externo.")
    if resp.status_code == 429:
        raise ServicioExternoError("Se alcanzó el límite de consultas del servicio externo. Intenta más tarde.")
    if resp.status_code >= 500:
        raise ServicioExternoError("El servicio externo presenta fallas temporales.")
    if resp.status_code != 200:
        raise ServicioExternoError(f"Respuesta inesperada del servicio externo (código {resp.status_code}).")

    try:
        data = resp.json()
    except ValueError as exc:
        raise ServicioExternoError("La respuesta del servicio externo no tiene un formato JSON válido.") from exc

    if not isinstance(data, dict):
        raise ServicioExternoError("Estructura de datos inesperada en la respuesta externa.")
    return data

def buscar_sugerencias_ciudades(texto: str, limite: int = 5) -> list[dict]:
    limpia = (texto or "").strip()
    if len(limpia) < 2 or not _PATRON_CIUDAD.match(limpia):
        return []

    geo_data = _peticion_get_json(
        "https://geocoding-api.open-meteo.com/v1/search",
        params={"name": limpia, "count": limite, "language": "es", "format": "json"},
    )
    sugerencias = []
    for item in geo_data.get("results") or []:
        nombre = item.get("name")
        if not nombre:
            continue
        sugerencias.append({
            "nombre": nombre,
            "region": item.get("admin1", ""),
            "pais": item.get("country", ""),
            "etiqueta": ", ".join(p for p in [nombre, item.get("admin1"), item.get("country")] if p),
        })
    return sugerencias


def obtener_clima_ciudad(ciudad: str) -> dict:
    ciudad_limpia = _validar_ciudad(ciudad)

    geo_data = _peticion_get_json(
        "https://geocoding-api.open-meteo.com/v1/search",
        params={"name": ciudad_limpia, "count": 1, "language": "es", "format": "json"},
    )
    resultados = geo_data.get("results") or []
    if not resultados:
        raise ServicioExternoError("No se encontró información geográfica para la ciudad ingresada.")

    ubicacion = resultados[0]
    lat = ubicacion.get("latitude")
    lon = ubicacion.get("longitude")
    nombre_resuelto = ubicacion.get("name", ciudad_limpia)
    pais = ubicacion.get("country", "")

    if lat is None or lon is None:
        raise ServicioExternoError("Coordenadas no disponibles para la ubicación consultada.")

    clima_data = _peticion_get_json(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": lat,
            "longitude": lon,
            "current": "temperature_2m,relative_humidity_2m,weather_code",
            "daily": "weather_code,temperature_2m_max,temperature_2m_min",
            "forecast_days": 3,
            "timezone": "auto",
        },
    )
    actual = clima_data.get("current") or {}
    diario = clima_data.get("daily") or {}

    if "temperature_2m" not in actual or "relative_humidity_2m" not in actual:
        raise ServicioExternoError("Datos climáticos incompletos en la respuesta del servicio.")

    codigo_wmo = actual.get("weather_code")
    estado = _CODIGOS_CLIMA.get(codigo_wmo, f"Código climático {codigo_wmo}")

    fechas = diario.get("time") or []
    codigos_d = diario.get("weather_code") or []
    maxs = diario.get("temperature_2m_max") or []
    mins = diario.get("temperature_2m_min") or []

    etiquetas_dias = ["Hoy", "Mañana", "Pasado mañana"]
    pronostico = []
    for i in range(min(3, len(fechas), len(codigos_d), len(maxs), len(mins))):
        pronostico.append({
            "etiqueta": etiquetas_dias[i],
            "fecha": fechas[i],
            "estado": _CODIGOS_CLIMA.get(codigos_d[i], f"Código {codigos_d[i]}"),
            "temp_min": mins[i],
            "temp_max": maxs[i],
        })

    return {
        "ciudad": nombre_resuelto,
        "pais": pais,
        "temperatura_c": actual["temperature_2m"],
        "humedad_pct": actual["relative_humidity_2m"],
        "estado_clima": estado,
        "pronostico": pronostico,
    }

def obtener_monedas_disponibles() -> list[tuple[str, str]]:
    ahora = time.time()
    if _CACHE_MONEDAS["monedas"] and ahora < _CACHE_MONEDAS["expira"]:
        return _CACHE_MONEDAS["monedas"]

    api_key = _obtener_api_key_monedas()
    url = f"https://v6.exchangerate-api.com/v6/{api_key}/codes"
    data = _peticion_get_json(url)

    if data.get("result") != "success":
        raise ServicioExternoError("No fue posible obtener el listado de monedas desde el proveedor.")

    codigos_raw = data.get("supported_codes") or []
    if not isinstance(codigos_raw, list) or not codigos_raw:
        raise ServicioExternoError("El listado de monedas recibido está vacío o incompleto.")

    monedas = []
    for par in codigos_raw:
        if isinstance(par, (list, tuple)) and len(par) >= 2:
            codigo = str(par[0]).strip().upper()
            nombre = str(par[1]).strip()
            if _PATRON_MONEDA.match(codigo):
                etiqueta = f"{codigo} — {nombre}" if nombre else codigo
                monedas.append((codigo, etiqueta))

    if not monedas:
        raise ServicioExternoError("No se encontraron códigos de moneda válidos en la respuesta.")

    monedas.sort(key=lambda item: item[0])
    _CACHE_MONEDAS["monedas"] = monedas
    _CACHE_MONEDAS["expira"] = ahora + 86400
    return monedas

def convertir_moneda(monto, moneda_origen: str, moneda_destino: str) -> dict:
    monto_validado = _validar_monto(monto)
    origen = _validar_moneda(moneda_origen, "moneda de origen")
    destino = _validar_moneda(moneda_destino, "moneda de destino")

    if origen == destino:
        return {
            "monto_origen": monto_validado,
            "moneda_origen": origen,
            "moneda_destino": destino,
            "tasa": 1.0,
            "monto_convertido": round(monto_validado, 2),
            "fecha": "hoy",
        }

    api_key = _obtener_api_key_monedas()
    url = f"https://v6.exchangerate-api.com/v6/{api_key}/pair/{origen}/{destino}/{monto_validado}"

    data = _peticion_get_json(url)

    if data.get("result") != "success":
        tipo_error = data.get("error-type", "")
        if tipo_error == "unsupported-code":
            raise ServicioExternoError("Una de las monedas ingresadas no es soportada por el servicio.")
        raise ServicioExternoError("No fue posible obtener la conversión desde el servicio de divisas.")

    if "conversion_result" not in data or "conversion_rate" not in data:
        raise ServicioExternoError("Respuesta incompleta del servicio de divisas.")

    return {
        "monto_origen": monto_validado,
        "moneda_origen": origen,
        "moneda_destino": destino,
        "tasa": round(float(data["conversion_rate"]), 6),
        "monto_convertido": round(float(data["conversion_result"]), 2),
        "fecha": data.get("time_last_update_utc", ""),
    }