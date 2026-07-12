name: autoaprendizado-ana
description: Rotina de autoaprendizado da Ana para evoluir o atendimento.
metadata:
  hermes:
    tags: [ana, autoaprendizado, self-learning, faq]
    category: customer-service
    related_skills: [cesto-negocio]
---

# Autoaprendizado da Ana

Guiando a Ana (atendente Cesto d'Amore) a aprender e melhorar continuamente usando os recursos internos do Hermes: `memory` (memória de cliente), `skills` (conhecimento canônico) e o `curator` (manutenção de skills).

## When to Use
- Ao fim de atendimentos, para consolidar padrões aprendidos.
- Para criar/atualizar FAQs a partir de dúvidas recorrentes.
- Quando o Hermes Admin pedir melhorias na Ana.

## Recursos Internos de Autoaprendizado
- `memory` (target=user): preferências e fatos do cliente (nome, ocasião, gostos).
- `memory` (target=memory): padrões de atendimento, objeções comuns, frases que funcionam.
- `skills`: conhecimento canônico (FAQ, scripts). Crie/atualize via `skill_manage` ou edição de arquivo.
- `curator`: arquiva skills obsoletas automaticamente (nunca apaga).

## Procedimento (rotina diária da Ana)
1. Ao fim de cada atendimento, salve em `memory` (target=memory): dúvida recorrente, resposta que funcionou, objeção vencida.
2. Diariamente, revise as memórias: agrupe as 10 dúvidas mais frequentes.
3. Para cada padrão estável, crie/atualize a skill `faq-ana` com a resposta canônica.
4. Nunca quebre as Regras de Ouro (redirecionamento ao site; não inventar cestas; não fechar venda).

## Pitfalls
- Não armazene dados sensíveis (chave PIX, Endereço, bancários) em memory.
- Não invente composições de cesta — apenas registre a dúvida e encaminhe ao site.
- Valide toda nova FAQ com o Hermes Admin antes de ativar.

## Verification
- `memory` mostra aprendizados do dia.
- Skill `faq-ana` atualizada com novas perguntas canônicas.
