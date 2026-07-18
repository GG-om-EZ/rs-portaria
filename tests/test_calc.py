from datetime import time
from decimal import Decimal

from app.calc import (
    Params,
    adicional_noturno_mensal,
    custo_profissional_continuo,
    minutos_noturnos,
)

PARAMS = Params(
    pct_encargos=Decimal("0.58"),
    pct_noturno=Decimal("0.20"),
    pct_margem=Decimal("0.10"),
    divisor_horas=220,
)


def test_minutos_noturnos_janela_22_06():
    assert minutos_noturnos(time(18, 0), time(6, 0)) == 480   # 22h-06h = 8h
    assert minutos_noturnos(time(22, 0), time(6, 0)) == 480
    assert minutos_noturnos(time(6, 0), time(18, 0)) == 0     # turno diurno
    assert minutos_noturnos(time(8, 0), time(17, 0)) == 0
    assert minutos_noturnos(time(20, 0), time(2, 0)) == 240   # 22h-02h = 4h
    assert minutos_noturnos(time(23, 0), time(7, 0)) == 420   # 23h-06h = 7h
    assert minutos_noturnos(time(2, 0), time(5, 0)) == 180    # madrugada: 02h-05h = 3h
    assert minutos_noturnos(time(0, 0), time(3, 0)) == 180    # 00h-03h = 3h
    assert minutos_noturnos(time(0, 0), time(0, 0)) == 480    # turno de 24h contém sempre 8h noturnas
    assert minutos_noturnos(time(6, 0), time(6, 0)) == 480


def test_adicional_noturno_mensal():
    # piso 2.200,00 e divisor 220 => hora = 10,00 exatos
    # turno 18-06: 8h noturnas x 15 plantões = 120h; 120h x 10,00 x 20% = 240,00
    assert adicional_noturno_mensal(
        220000, time(18, 0), time(6, 0), 15, PARAMS
    ) == 24000


def test_custo_profissional_continuo_noturno():
    assert custo_profissional_continuo(
        220000, time(18, 0), time(6, 0), 15, PARAMS
    ) == 244000  # piso + adicional


def test_custo_profissional_continuo_diurno_sem_adicional():
    assert custo_profissional_continuo(
        220000, time(6, 0), time(18, 0), 15, PARAMS
    ) == 220000


def test_encargos_e_margem():
    from app.calc import encargos_centavos, margem_centavos

    assert encargos_centavos(514910, PARAMS) == 298648   # 0.58 x 5.149,10 = 2.986,478 -> HALF_UP
    assert margem_centavos(1041558, PARAMS) == 104156    # 0.10 x 10.415,58

    zero = Params(Decimal("0"), Decimal("0"), Decimal("0"))
    assert encargos_centavos(100000, zero) == 0
    assert margem_centavos(100000, zero) == 0
