# Calibração dos fluxos completos

Os JSON desta pasta mostram diferenças de representação que não alteraram o
conteúdo: ordem das guias e valores numéricos de profundidade equivalentes à
ordem explícita das camadas. A conferência usa os mesmos comparadores semânticos
das etapas de cópia/histórico e recuperação, conservando todos os demais campos,
assets e sua multiplicidade. Não há tolerância na comparação de pixels.

Também foram corrigidas suposições do driver sobre o nome do modo público
(`none`), API de colagem, acesso ao bloqueio dos itens, escolha de uma camada
que pudesse ser reordenada e preservação da proteção no salvamento. Esses erros
de preparação não representam falhas observadas na versão final do produto.

A pasta vizinha `diagnostico` tem somente uma amostra por cenário, usada para
validar o instrumento. Não integra a medição final de vinte/cinco amostras.
