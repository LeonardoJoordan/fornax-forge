# Otimizações Pareto do editor

09/10/2026. Foram mantidas três intervenções locais: compartilhamento dos
pixels transparentes das formas, economia de consultas geométricas no
roteamento e menor trabalho de compressão na recuperação automática.

A troca de páginas teve a maior redução de tempo e memória. Recuperações
com imagens grandes também melhoraram. Os conectores tiveram ganho menor;
o cenário denso com 1.000 cartões em 100 conjuntos continua levando segundos
para atualizar uma posição e não está certificado como uma edição fluida.

## O que mudou e por quê

### Formas e troca de páginas

Cada forma reservava um pixmap transparente de 1.000 × 1.000 pixels, embora
seu desenho seja vetorial. Quarenta formas representavam cerca de 153 MiB de
buffers, impedindo a retenção de uma cena no orçamento de 64 MiB.

Agora as formas compartilham um único buffer vazio de aproximadamente
3,8 MiB por aplicação. Dimensões lógicas, máscaras e escalas permanecem
iguais; a escrita numa cópia desanexa os pixels e não afeta os outros itens.
Não são compartilhadas imagens pessoais por esse mecanismo.

A retenção de cenas também verifica primeiro o orçamento. A conferência
dos assets, fonte, tema e autorização continua obrigatória antes de guardar
uma cena elegível. No cenário de 200 objetos, a cena passou de não retida
para retida, com estimativa de 19,17 MiB, dentro do mesmo limite anterior.

### Conectores

O roteamento reutiliza respostas de interseção com obstáculos fixos dentro
de um único cálculo. O cache tem no máximo 16.384 consultas e não permanece
entre geometrias. Coordenadas não são arredondadas; exclusões de blocos
participam da chave. Canais de outras conexões continuam sendo conferidos
contra o estado atualizado a cada ligação.

A busca também dispensa calcular a penalidade de cruzamento de um segmento
já rejeitado por estar bloqueado. O algoritmo, as portas permitidas, a ordem
das conexões, as tolerâncias e as regras de obstáculos permanecem iguais.

### Recuperação automática

Somente a recuperação pode armazenar PNG/JPEG de pelo menos 256 KiB sem
uma nova camada de compressão ZIP. Esses arquivos já possuem compressão
própria. JSON, SVG, imagens pequenas e o salvamento manual mantêm a política
anterior. O formato já aceitava entradas ZIP armazenadas sem compressão.

Criptografia, autorização, verificação do conteúdo, validação do arquivo
original, backup, fsync e publicação atômica foram preservados. Assets
protegidos continuam dentro do conteúdo criptografado. Perto dos limites
do ZIP interno ou do pacote combinado, a recuperação tenta novamente a
compressão original; nenhum limite foi ampliado.

## Medições

Linux no ThinkPad, Qt offscreen, escala 1, Inter e tema escuro. Processos
isolados, dados sintéticos, duas preparações e cinco amostras por cenário
e versão. Testes pesados não foram executados junto das medições. São
medianas observadas, não promessas para toda máquina ou documento.

| Operação | Antes | Depois | Redução de tempo |
|---|---:|---:|---:|
| Uma ida e volta entre páginas de 200 objetos | 11.932,79 ms | 1.959,00 ms | 83,6% |
| Calcular rotas de 100 blocos e 99 conexões | 4.141,94 ms | 3.566,01 ms | 13,9% |
| Mover um conjunto, registrar histórico e pintar um quadro de 1.000 cartões em 100 conjuntos | 3.560,64 ms | 3.268,88 ms | 8,2% |
| Recuperação pública com imagens grandes | 374,28 ms | 188,01 ms | 49,8% |
| Recuperação de assinaturas com imagens grandes | 403,14 ms | 234,30 ms | 41,9% |
| Recuperação integral com imagens grandes | 384,54 ms | 215,73 ms | 43,9% |
| Recuperação pública pequena | 47,60 ms | 52,50 ms | **10,3% mais lenta nesta rodada** |

Na troca de páginas, o RSS observado ao final caiu de **486,52 para
176,57 MiB**, aproximadamente 64%. Isso mede memória residente naquele
momento, não o pico da operação. O número inclui Qt, Python e caches.

A pintura isolada do quadro inteiro de 1.000 cartões variou de 56,41 para
53,42 ms. Não foi alterada nesta rodada; essa pequena diferença não deve
ser atribuída às otimizações do roteamento. O deslocamento medido muda
diretamente a posição do item, respeita o magnetismo, registra o histórico
e aguarda a pintura; não simula uma sequência contínua de mouse físico.

Os pacotes de recuperação com imagens grandes ficaram aproximadamente
0,03% menores na fixture, porque a recompressão acrescentava ligeiro custo
de armazenamento. Outros PNG/JPEG podem produzir pacotes maiores; essa
política não garante redução do tamanho dos arquivos.

Valores completos, p95 e conferências: [comparacao.json](comparacao.json).
Tamanhos: [tamanhos-recuperacao.json](tamanhos-recuperacao.json).

## Resultados piores e limites

- A recuperação pequena aumentou cerca de 5 ms na primeira rodada. Uma
  repetição independente com 20 amostras por versão registrou **60,47 →
  58,89 ms**, com p95 **79,35 → 72,22 ms**. A piora não foi consistente.
  A compressão desses arquivos não mudou; não há evidência para atribuir
  os 5 ms a novas verificações de segurança. Os resultados originais
  permanecem registrados e não foram substituídos pela repetição.
- O RSS do processo de roteamento isolado aumentou de 69,49 para 73,07 MiB.
  Há um cache transitório limitado; a diferença também inclui o alocador.
  No editor com 1.000 cartões, o RSS observado variou de 132,86 para
  133,19 MiB. Não se conclui vazamento nem memória de pico desses números.
- O cenário de 100 conjuntos e 99 conexões ainda é lento para mover um
  item: aproximadamente 3,27 s. Os caminhos dessa fixture cruzam várias
  regiões do quadro. A melhoria de 8,2% não autoriza dizer que qualquer
  quadro com até 100 conjuntos funcionará sem dificuldade.
- O cenário contém 1.000 posições usando o cartão compartilhado do editor.
  Não certifica a geração com 1.000 fotografias individuais. Os testes
  anteriores de 2.500 cartões usavam um conjunto, não 100 conjuntos.
- A galeria não foi alterada: manter miniaturas previamente geradas e sua
  compatibilidade com fontes/modelos amplia o trabalho para beneficiar
  sobretudo a primeira abertura. Outro modo de proxy, alteração ampla do
  algoritmo e conexões provisórias durante arraste também ficaram fora
  desta rodada de intervenções pequenas.

## Fidelidade e testes

- Os 117 testes direcionados executados antes passaram. Os mesmos módulos
  passaram depois, assim como nove novos testes das otimizações.
- A suíte ampla posterior executou **209 testes**, sem falhas, incluindo
  testes que também fazem parte dos módulos direcionados. As quantidades
  não devem ser somadas como se fossem testes distintos.
- Entradas e fontes coincidiram nas sete comparações. Os hashes dos estados
  conferidos, incluindo pixels quando capturados, foram iguais antes e
  depois. As coordenadas das rotas e os indicadores de congestionamento
  também coincidiram. Ambas as páginas foram comparadas, e o cenário de
  1.000 cartões verificou Undo/Redo.
- Os contratos da recuperação incluem conteúdo e assets, original
  preservado, cancelamento, revogação de autorização, concorrência,
  encerramento, backup e falhas de gravação. Os novos testes conferem
  também o retorno à compressão original nos limites interno, externo e
  combinado de assets públicos/protegidos.
- A validação foi automatizada em Qt offscreen. Mouse/touchpad no aplicativo
  nativo, Windows e uso prolongado com dados reais não foram certificados.

Registros em `checks-antes/`, `checks-depois/`, `checks-final/`,
`checks-limite/`, `checks-novos/` e [regressoes-finais.log](regressoes-finais.log).
A repetição pequena está em `repeticao-pequeno/`.

## Instrumentos e reprodução

O driver detectou e corrigiu dois problemas antes das alterações de produto:
o identificador interno do modo público é `none`, e alguns deslocamentos
iniciais não moviam o item por causa do magnetismo. A referência válida
usa duas células por deslocamento no quadro e exige mudança de posição.
As amostras inválidas ficaram em `diagnostico-instrumentos/` e não entram
nas comparações. Os caminhos de execução de `page-200` e `routing-100`
não foram alterados por essa calibração dos outros cenários.

```bash
.venv/bin/python tests/performance/benchmark_pareto.py --output /tmp/fornax-pareto-medicao --label depois --samples 5
.venv/bin/python tests/performance/run_pareto_checks.py --output /tmp/fornax-pareto-testes
.venv/bin/python tests/performance/run_regressions.py --include-contracts --output /tmp/fornax-pareto-regressoes.log
```

Não executar suítes pesadas em paralelo com as medições. Para uma nova
comparação, restaurar a referência somente em uma cópia isolada do projeto.
O patch exclusivo desta rodada está em [alteracoes-pareto.patch](alteracoes-pareto.patch);
os hashes anteriores e posteriores estão em
[identidade-alteracoes.json](identidade-alteracoes.json).
As alterações das etapas anteriores e os modelos pessoais foram preservados.
