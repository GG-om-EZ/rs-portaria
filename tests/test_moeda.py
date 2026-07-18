import pytest

from app.moeda import format_brl, parse_brl


def test_parse_brl_formatos_comuns():
    assert parse_brl("1.853,00") == 185300
    assert parse_brl("R$ 1.140,50") == 114050
    assert parse_brl("580") == 58000
    assert parse_brl("12.000") == 1200000
    assert parse_brl("0,50") == 50


def test_parse_brl_invalido():
    with pytest.raises(ValueError):
        parse_brl("abc")
    with pytest.raises(ValueError):
        parse_brl("")


def test_parse_brl_so_pontuacao():
    # Entrada só de pontuação não pode parsear como 0
    with pytest.raises(ValueError):
        parse_brl(".")
    with pytest.raises(ValueError):
        parse_brl(",")
    with pytest.raises(ValueError):
        parse_brl("..")


def test_parse_brl_multiplas_virgulas():
    # Mais de uma vírgula é ambíguo — rejeitar em vez de misparsear
    with pytest.raises(ValueError):
        parse_brl("1,853,00")


def test_parse_brl_ponto_decimal_teclado_movel():
    # Teclado numérico móvel usa "." como separador decimal — um único ponto
    # seguido de 1-2 dígitos no fim, sem vírgula, deve ser tratado como decimal
    assert parse_brl("1853.00") == 185300
    assert parse_brl("1.50") == 150
    assert parse_brl("0.5") == 50
    # grupos de 3 dígitos continuam sendo interpretados como milhar (inalterado)
    assert parse_brl("12.000") == 1200000
    # com vírgula presente, o comportamento não muda
    assert parse_brl("1.853,00") == 185300


def test_parse_brl_ponto_ambiguo_invalido():
    with pytest.raises(ValueError):
        parse_brl(".50")
    with pytest.raises(ValueError):
        parse_brl("1.2.50")


def test_format_brl():
    assert format_brl(185300) == "1.853,00"
    assert format_brl(50) == "0,50"
    assert format_brl(1200000) == "12.000,00"
    assert format_brl(0) == "0,00"
    assert format_brl(-185300) == "-1.853,00"


def test_ida_e_volta():
    assert parse_brl(format_brl(999999999)) == 999999999
