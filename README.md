# RS Portaria — Gerador de Propostas

Ferramenta web self-hosted para gerar propostas comerciais (serviço contínuo e
evento único) em PDF, com cálculo automático, override destacado, linhas de
custo manuais e checklist bloqueante.
Roteiro de aceitação com o sócio: `docs/verificacao-manual.md`.

## Uso diário

```bash
cp .env.example .env   # primeira vez: edite PIN, segredo e IP do Tailscale
docker compose up -d   # sobe em http://<ip-tailscale>:8420
docker compose down    # derruba após o uso
```

O PDF emitido é baixado no navegador de quem gerou e uma cópia é gravada
automaticamente na pasta `03-Propostas-Enviadas` (volume `RSP_ARQUIVO_HOST`).

## Desenvolvimento

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
APP_PIN=1234 APP_SECRET=dev .venv/bin/uvicorn app.main:app --reload
.venv/bin/python -m pytest -q   # testes (PDF exige libs do WeasyPrint; roda no container)
```

## Backup

Todo o estado vive em `./data/rsportaria.db` — copie esse arquivo.
A pasta de PDFs arquivados (`RSP_ARQUIVO_HOST`) também merece backup por
conveniência, embora seus PDFs sejam regeneráveis a partir do banco a
qualquer momento pelo botão "Regravar cópias não arquivadas".

## Acesso remoto do sócio (Tailscale)

1. Crie uma conta em https://tailscale.com e instale no notebook:
   `sudo pacman -S tailscale && sudo systemctl enable --now tailscaled && sudo tailscale up`.
2. Descubra o IP do notebook: `tailscale ip -4` (ex.: 100.101.102.103) e
   coloque em `RSP_BIND` no `.env`.
3. No celular do sócio: instale o app Tailscale (Play Store), faça login na
   MESMA conta, ative o toggle.
4. Salve nos favoritos do navegador dele: `http://100.101.102.103:8420`.
5. O acesso só funciona com o container UP e o Tailscale ativo nos dois lados.
   Nada fica exposto à internet pública.

## Migração futura (VPS/Raspberry Pi)

O serviço é o mesmo em qualquer host: copie o repositório + `./data` +
`.env` (ajustando `RSP_ARQUIVO_HOST`) e rode `docker compose up -d`.

## Licença

Distribuído sob a **GNU Affero General Public License v3.0** (AGPL-3.0) — ver
[`LICENSE`](LICENSE).

Copyright (C) 2026 RS Portaria e Serviços.

Este programa é software livre: você pode redistribuí-lo e/ou modificá-lo sob os
termos da AGPL-3.0 publicada pela Free Software Foundation. Por ser uma aplicação
de rede, quem executar uma versão modificada acessível por rede deve
disponibilizar o código-fonte correspondente aos usuários dessa versão (AGPL §13).
