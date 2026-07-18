"""Motor de cálculo puro. Centavos int; Decimal para percentuais; ROUND_HALF_UP."""
from dataclasses import dataclass
from datetime import time
from decimal import ROUND_HALF_UP, Decimal

# Janela legal do adicional noturno: 22h às 06h
_NOTURNO_INICIO_MIN = 22 * 60
_NOTURNO_FIM_MIN = (24 + 6) * 60


@dataclass(frozen=True)
class Params:
    pct_encargos: Decimal
    pct_noturno: Decimal
    pct_margem: Decimal
    divisor_horas: int = 220


def _para_centavos(valor: Decimal) -> int:
    return int(valor.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def minutos_noturnos(inicio: time, fim: time) -> int:
    """Minutos do turno dentro da janela 22h-06h. Turno pode cruzar a meia-noite."""
    ini = inicio.hour * 60 + inicio.minute
    fi = fim.hour * 60 + fim.minute
    if fi <= ini:  # cruza meia-noite
        fi += 24 * 60
    total = 0
    # A janela repete a cada 24h; o deslocamento negativo cobre a cauda da
    # noite anterior ([-2h, 6h)) para turnos que começam na madrugada
    for desloc in (-24 * 60, 0, 24 * 60):
        j_ini = _NOTURNO_INICIO_MIN + desloc
        j_fim = _NOTURNO_FIM_MIN + desloc
        total += max(0, min(fi, j_fim) - max(ini, j_ini))
    return total


def adicional_noturno_mensal(
    piso_centavos: int, inicio: time, fim: time, plantoes_mes: int, params: Params
) -> int:
    horas_noturnas_mes = Decimal(minutos_noturnos(inicio, fim) * plantoes_mes) / 60
    valor_hora = Decimal(piso_centavos) / params.divisor_horas
    return _para_centavos(horas_noturnas_mes * valor_hora * params.pct_noturno)


def custo_profissional_continuo(
    piso_centavos: int, inicio: time, fim: time, plantoes_mes: int, params: Params
) -> int:
    return piso_centavos + adicional_noturno_mensal(
        piso_centavos, inicio, fim, plantoes_mes, params
    )


def encargos_centavos(base_centavos: int, params: Params) -> int:
    """Encargos sociais: percentual sobre a soma da mão de obra."""
    return _para_centavos(Decimal(base_centavos) * params.pct_encargos)


def margem_centavos(base_centavos: int, params: Params) -> int:
    """Margem administrativa: percentual sobre mão de obra + acessórios + encargos."""
    return _para_centavos(Decimal(base_centavos) * params.pct_margem)
