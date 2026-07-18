"""Sessão por PIN: cookie assinado com HMAC do segredo da aplicação."""
import hashlib
import hmac

_MENSAGEM = b"sessao-rsportaria"


def assinar_sessao(secret: str) -> str:
    return hmac.new(secret.encode(), _MENSAGEM, hashlib.sha256).hexdigest()


def sessao_valida(token: str | None, secret: str) -> bool:
    if not token:
        return False
    return hmac.compare_digest(token, assinar_sessao(secret))
