# Roteiro de verificação manual ponta a ponta

Verificação de aceitação da v1/v1.1 do gerador de propostas, executada pelo
usuário junto com o sócio (no celular dele, via Tailscale). Marque cada caixa
ao confirmar o resultado esperado. Divergências vão na seção final.

## 0. Pré-requisitos (uma única vez)

- [ ] Tailscale ativo no notebook: `sudo systemctl enable --now tailscaled && sudo tailscale up`;
      anote o IP com `tailscale ip -4`.
- [ ] Tailscale no celular do sócio: app da Play Store, login na **mesma conta**, toggle ativo.
- [ ] `.env` definitivo (não use os valores de exemplo):
  - `APP_PIN`: PIN forte de 6 dígitos, combinado com o sócio por voz (não por escrito no WhatsApp).
  - `APP_SECRET`: gere com `openssl rand -hex 32`.
  - `RSP_BIND`: o IP do Tailscale anotado acima.
  - `RSP_ARQUIVO_HOST`: caminho local da pasta `03-Propostas-Enviadas`.
- [ ] Suba o serviço: `docker compose up -d`.

## 1. Acesso do celular

- [ ] No celular do sócio, abrir `http://<ip-tailscale>:8420` → tela de login aparece.
- [ ] PIN errado é recusado; PIN correto entra na home.
- [ ] Salvar o endereço nos favoritos do navegador do sócio.

## 2. Fluxo contínuo completo - números de referência

Reproduz a proposta de referência (serviço contínuo) no app, de ponta a ponta, pelo celular.

1. [ ] Home → Nova proposta → **Serviço contínuo**.
2. [ ] Cliente: criar "Cliente Exemplo Ltda", CNPJ `11.222.333/0001-81`,
       Av. Exemplo, 1000. CNPJ com dígito errado deve ser recusado.
3. [ ] Local: endereço do serviço, duração 12 meses, data de início.
4. [ ] Serviços: turno `18:00`-`06:00`, 15 plantões;
       **Portaria noturna (12x36) × 2** e **Portaria diurna (12x36) × 1**.
5. [ ] Custos - a tabela deve mostrar Alimentação (3 × 580,00) e Transporte
       (3 × 180,00) automáticos. Ajustar para os valores fechados do documento real:
   - Portaria noturna → sobrescrever para **1.853,00** (linha fica destacada, sugerido visível).
   - Portaria diurna → confirmar **1.600,00**.
   - Encargos sociais → sobrescrever para **3.066,00**.
   - Margem administrativa → sobrescrever para **1.140,00**.
   - **Adicionar linha de custo**: descrição "Operacional", valor **208,00**.
6. [ ] **Total = R$ 12.000,00** (igual ao documento de referência).
7. [ ] Pagamento: formas + vencimento. Revisão: checklist todo verde → **Emitir**.
8. [ ] Número no formato `RS-2026-NNNN`; PDF baixa no celular; cópia aparece em
       `03-Propostas-Enviadas/` no notebook (sincronizada via Syncthing).

## 3. Fluxo evento completo - números reais do orçamento de evento

1. [ ] Nova proposta → **Evento único**; cliente qualquer; data e horários do evento.
2. [ ] Serviços: **Segurança de evento (12h) × 6** e **Serviços gerais de evento (12h) × 2**.
3. [ ] Custos - Alimentação (8 × 20,00) e Transporte (8 × 40,00) automáticos. Ajustar:
   - Encargos sociais → sobrescrever para **0,00**.
   - Margem administrativa → sobrescrever para **0,00**.
   - **Adicionar linha de custo**: "EPIs, trajes e material de limpeza", valor **160,00**.
4. [ ] **Total = R$ 2.400,00** (igual ao modelo real).
5. [ ] Emitir e conferir no PDF as seções específicas de evento: data-limite de
       pagamento antecipado e condições de evento.

## 4. Override, linha manual e checklist bloqueante

- [ ] Sobrescrever uma linha → destaque visual + "sugerido" exibido; o botão **voltar** restaura o valor.
- [ ] Remover uma linha manual pelo botão **x** → some da tabela e do total. O botão **x** só
      aparece em linhas adicionadas manualmente.
- [ ] Linha manual com descrição vazia ou valor ilegível → mensagem de erro, nada é criado.
- [ ] Tentar emitir sem forma de pagamento → emissão bloqueada com o item do
      checklist em vermelho.

## 5. Duplicar e reemitir

- [ ] Duplicar uma proposta emitida → abre rascunho novo com tudo copiado
      (inclusive linhas manuais e overrides).
- [ ] Alterar algo e emitir → recebe número novo; a proposta original permanece intacta.

## 6. Admin - parâmetros com vigência

- [ ] Em Configurações, reajustar um piso com vigência futura.
- [ ] Rascunho novo criado hoje usa o valor vigente (antigo); a proposta emitida
      anterior não muda.

## 7. Registro de divergências

Anote aqui tudo que parecer errado, feio ou confuso durante a execução -
especialmente sobre o visual do PDF, que é a próxima frente de trabalho
(estão previstas 2-3 variações de layout para escolha):

- _(vazio)_
