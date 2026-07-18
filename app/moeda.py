"""Conversão entre texto em reais (pt-BR) e centavos inteiros."""
import re


def parse_brl(texto: str) -> int:
    """'1.853,00' -> 185300. Sem vírgula, assume valor inteiro em reais."""
    limpo = texto.strip().replace("R$", "").strip()
    # Exige ao menos um dígito - rejeita entradas só de pontuação (".", ",", "..")
    if not re.fullmatch(r"(?=.*\d)[\d.,]+", limpo):
        raise ValueError(f"Valor monetário inválido: {texto!r}")
    # Mais de uma vírgula é ambíguo (ex.: "1,853,00") - rejeita em vez de misparsear
    if limpo.count(",") > 1:
        raise ValueError(f"Valor monetário inválido: {texto!r}")
    if "," in limpo:
        inteiro, _, decimal = limpo.partition(",")
        decimal = (decimal + "00")[:2]
        inteiro = inteiro.replace(".", "")
    else:
        n_pontos = limpo.count(".")
        if n_pontos == 0:
            inteiro, decimal = limpo, "00"
        else:
            ultimo_grupo = limpo.rsplit(".", 1)[1]
            if n_pontos == 1 and len(ultimo_grupo) in (1, 2):
                # teclado numérico móvel: único ponto seguido de 1-2 dígitos no
                # fim é decimal ("1853.00" -> R$1.853,00; "1.50" -> R$1,50)
                inteiro, _, decimal = limpo.rpartition(".")
            elif len(ultimo_grupo) in (1, 2):
                # múltiplos pontos sem vírgula com grupo final não-milhar: ambíguo
                raise ValueError(f"Valor monetário inválido: {texto!r}")
            else:
                inteiro, decimal = limpo, "00"
            inteiro = inteiro.replace(".", "")
            decimal = (decimal + "00")[:2]
    if not (inteiro.isdigit() and decimal.isdigit()):
        raise ValueError(f"Valor monetário inválido: {texto!r}")
    return int(inteiro) * 100 + int(decimal)


def format_brl(centavos: int) -> str:
    """185300 -> '1.853,00' (sem prefixo R$)."""
    negativo = centavos < 0
    centavos = abs(centavos)
    reais, cents = divmod(centavos, 100)
    milhar = f"{reais:,}".replace(",", ".")
    return f"{'-' if negativo else ''}{milhar},{cents:02d}"
