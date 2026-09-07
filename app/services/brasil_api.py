import logging
import re

log = logging.getLogger(__name__)


def only_digits(value):
    return re.sub(r"\D", "", value or "")


def looks_like_cnpj(value):
    return len(only_digits(value)) == 14


def looks_like_cpf(value):
    return len(only_digits(value)) == 11


def looks_like_cep(value):
    return len(only_digits(value)) == 8


def format_cnpj(value):
    d = only_digits(value)
    if len(d) == 14:
        return f"{d[0:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:14]}"
    return value


def format_cep(value):
    d = only_digits(value)
    if len(d) == 8:
        return f"{d[0:5]}-{d[5:8]}"
    return value


def _get_json(url, timeout=8):
    import urllib.request

    req = urllib.request.Request(url, headers={"User-Agent": "OpenPOS/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


class BrazilApiService:
    def _raw_cnpj(self, cnpj, timeout=8):
        d = only_digits(cnpj)
        if not looks_like_cnpj(d):
            return None
        try:
            data = _get_json(f"https://brasilapi.com.br/api/cnpj/v1/{d}", timeout)
            import json

            return json.loads(data)
        except Exception as e:
            log.warning("Brasil API CNPJ falhou: %s", e)
            return None

    def fetch_cnpj(self, cnpj):
        raw = self._raw_cnpj(cnpj)
        if not raw:
            return None
        estado = (raw.get("uf") or "").upper()
        return {
            "name": raw.get("razao_social") or raw.get("nome_fantasia") or "",
            "fantasy": raw.get("nome_fantasia") or "",
            "document": format_cnpj(cnpj),
            "entity_type": "PJ",
            "cep": format_cep(raw.get("cep") or ""),
            "address": raw.get("logradouro") or "",
            "number": raw.get("numero") or "",
            "complement": raw.get("complemento") or "",
            "neighborhood": raw.get("bairro") or "",
            "city": raw.get("municipio") or "",
            "state": estado,
            "phone": raw.get("ddd_telefone_1") or "",
            "email": raw.get("email") or "",
        }

    def fetch_cep(self, cep):
        d = only_digits(cep)
        if not looks_like_cep(d):
            return None
        try:
            data = _get_json(f"https://brasilapi.com.br/api/cep/v1/{d}")
            import json

            data = json.loads(data)
            return {
                "cep": format_cep(d),
                "address": data.get("street") or "",
                "neighborhood": data.get("neighborhood") or "",
                "city": data.get("city") or "",
                "state": data.get("state") or "",
            }
        except Exception as e:
            log.warning("Brasil API CEP falhou: %s", e)
            return None


brazil_api_service = BrazilApiService()
