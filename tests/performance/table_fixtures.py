"""Especificações sintéticas de aceitação; ainda não são modelos .fornax.

Não define o schema persistente das tabelas nem desenha itens no aplicativo.
Medidas em mm e conteúdo esperado descrevem entradas estáveis para o protótipo.
"""
from copy import deepcopy
import argparse
from hashlib import sha256
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def table_spec(identifier, rows, columns, *, merged=()):
    covered = set()
    anchors = {}
    for row, column, row_span, column_span in merged:
        area = {(r, c) for r in range(row, row + row_span)
                for c in range(column, column + column_span)}
        assert row_span > 0 and column_span > 0
        assert all(0 <= r < rows and 0 <= c < columns for r, c in area)
        assert not covered.intersection(area)
        covered.update(area)
        anchors[row, column] = (row_span, column_span)
    cells = []
    for row in range(rows):
        for column in range(columns):
            if (row, column) in covered and (row, column) not in anchors:
                continue
            row_span, column_span = anchors.get((row, column), (1, 1))
            cells.append(dict(key=f'{identifier}-r{row + 1}c{column + 1}', row=row,
                              column=column, row_span=row_span, column_span=column_span,
                              html='<p></p>', align='left', vertical_align='top',
                              wrap=True, fill='#ffffff'))
    return dict(key=identifier, rows=rows, columns=columns, origin_mm=[15, 25],
                column_widths_mm=[180 / columns] * columns, row_heights_mm=[12] * rows,
                default_font='Inter', default_font_size_pt=10, padding_mm=1.5,
                outline=dict(color='#203746', width_mm=0.3), cells=cells)


def cell(table, row, column, html, **style):
    target = next(c for c in table['cells'] if (c['row'], c['column']) == (row, column))
    target.update(html=html, **style)
    return target['key']


def fixture(identifier, purpose, pages, records, expectations, exercises):
    return dict(fixture_format='fornax-table-acceptance-spec', fixture_version=1,
                id=identifier, purpose=purpose, runtime_model=False,
                physical_page_mm=[210, 297], pages=pages, records=records,
                expected_resolved_text=expectations, exercises=exercises)


def cases():
    table = table_spec('boletim', 10, 6, merged=((0, 0, 1, 6), (8, 0, 1, 6), (9, 0, 1, 6)))
    cell(table, 0, 0, '<p><b>BOLETIM — {aluno}</b></p>', align='center',
         vertical_align='center', fill='#dde9f0')
    for col, label in enumerate(('Disciplina', '1º bim.', '2º bim.', '3º bim.', '4º bim.', 'Situação')):
        cell(table, 1, col, f'<p><b>{label}</b></p>', fill='#edf2f5', align='center')
    subjects = (('Português', 'portugues'), ('Matemática', 'matematica'),
                ('Ciências', 'ciencias'), ('História', 'historia'),
                ('Geografia', 'geografia'), ('Artes', 'artes'))
    for row, (label, field) in enumerate(subjects, 2):
        cell(table, row, 0, f'<p>{label}</p>')
        for col in range(1, 5):
            cell(table, row, col, '<p><b>{' + field + f'_b{col}' + '}</b></p>',
                 align='center', vertical_align='center')
        cell(table, row, 5, '<p>{' + field + '_situacao}</p>')
    cell(table, 8, 0, '<p>Observações: {observacao}</p>')
    cell(table, 9, 0, '<p>Turma: {turma} — Ano: {ano}</p>', align='right')
    full = dict(aluno='Aluno Sintético A', turma='Turma A', ano='2026', observacao='Participação regular.\nBom desenvolvimento.')
    for _, field in subjects:
        full.update({f'{field}_b{col}': str(6 + col) for col in range(1, 5)})
        full[field + '_situacao'] = 'Registrado'
    empty = deepcopy(full)
    empty.update(aluno='Aluno Sintético B', matematica_b1=0, portugues_b2='', observacao='')
    boletim = fixture('boletim', 'Notas fornecidas por placeholders; sem cálculo de médias.',
                      [dict(page='front', tables=[table])],
                      [dict(key='completo', values=full), dict(key='vazio-e-zero', values=empty)],
                      {'vazio-e-zero': {'boletim-r3c3': '', 'boletim-r4c2': '0',
                                         'boletim-r9c1': 'Observações: '}},
                      ['Campos em negrito', 'Valores vazios não removem grade',
                       'Zero numérico', 'Quebra manual', 'Título mesclado', 'Alinhamentos'])

    table = table_spec('escala', 8, 5, merged=((0, 0, 1, 5), (7, 0, 1, 5)))
    cell(table, 0, 0, '<p><b>ESCALA — {periodo}</b></p>', align='center', fill='#e4eee5')
    for col, label in enumerate(('Data', 'Turno', 'Responsável', 'Função', 'Observação')):
        cell(table, 1, col, f'<p><b>{label}</b></p>', fill='#eef4ef')
    values = dict(periodo='Período Sintético 01', nota_geral='Conferir os horários.')
    for row in range(2, 7):
        slot = row - 1
        for col, field in enumerate(('data', 'turno', 'responsavel', 'funcao', 'observacao')):
            cell(table, row, col, '<p>{' + f'{field}_{slot}' + '}</p>')
            values[f'{field}_{slot}'] = {'data': f'{slot:02d}/11/2026', 'turno': 'Manhã',
                                       'responsavel': f'Pessoa Sintética {slot}',
                                       'funcao': 'Apoio', 'observacao': ''}[field]
    cell(table, 7, 0, '<p>Nota geral: {nota_geral}</p>')
    escala = fixture('escala', 'Cinco posições fixas preenchidas por um registro; sem repetição automática.',
                     [dict(page='front', tables=[table])],
                     [dict(key='fixo', values=values)], {},
                     ['Adicionar/remover linha e coluna', 'Formatação de intervalo',
                      'Contornos internos/externos', 'Copiar intervalo tabular'])

    table = table_spec('mesclagens', 4, 4,
                       merged=((0, 0, 1, 4), (1, 0, 2, 1), (1, 1, 1, 2), (3, 2, 1, 2)))
    cell(table, 0, 0, '<p><b>QUADRO — {no</b><b>me}</b></p>', align='center', fill='#f0e8d7')
    cell(table, 1, 0, '<p>Área<br/>Sintética</p>', vertical_align='center')
    cell(table, 1, 1, '<p><i>Texto combinado</i> e <b>{funcao}</b></p>', vertical_align='bottom')
    cell(table, 1, 3, '<p>AVISO DE EXCESSO ' + ('texto longo ' * 20) + '</p>', wrap=False)
    cell(table, 2, 1, '<p>Ação ágil 😀 𝄞</p>', align='right')
    cell(table, 2, 2, '<p>|Contato: {contato}|</p>')
    cell(table, 2, 3, '<p>Nota: {nota}</p>')
    cell(table, 3, 0, '<p><b>Texto A</b></p>')
    cell(table, 3, 1, '<p><i>Texto B</i></p>')
    cell(table, 3, 2, '<p>Rodapé<br/>Linha seguinte</p>', align='center', vertical_align='bottom')
    merged = fixture('mesclagens', 'Grade com mesclagens horizontais/verticais e conteúdo para operações destrutivas reversíveis.',
                     [dict(page='front', tables=[table])],
                     [dict(key='vazio', values=dict(nome='Pessoa Sintética', funcao='Apoio', contato='', nota=''))],
                     {'vazio': {'mesclagens-r1c1': 'QUADRO — Pessoa Sintética',
                                'mesclagens-r3c3': '', 'mesclagens-r3c4': 'Nota: '}},
                     ['Mesclar células preenchidas', 'Dividir e desfazer são operações distintas',
                      'Inserir/remover cruzando mesclagem', 'Unicode UTF-16',
                      'Placeholder dividido entre spans', 'Bloco opcional', 'Overflow sem invasão'])

    front = table_spec('frente', 3, 3, merged=((0, 0, 1, 3),))
    cell(front, 0, 0, '<p><b>FICHA — {nome}</b></p>', align='center')
    cell(front, 1, 0, '<p>Identificação</p>')
    cell(front, 1, 1, '<p>{identificacao}</p>')
    back = table_spec('verso', 4, 2, merged=((0, 0, 1, 2),))
    cell(back, 0, 0, '<p><b>INFORMAÇÕES COMPLEMENTARES</b></p>', align='center')
    cell(back, 1, 0, '<p>Campo exclusivo do verso</p>')
    cell(back, 1, 1, '<p><b>{campo_verso}</b></p>')
    cell(back, 2, 1, '<p>Observação: {observacao_verso}</p>')
    duplex = fixture('frente-verso', 'Duas páginas independentes, campos exclusivos do verso e recuperação de texto ativo.',
                     [dict(page='front', tables=[front]), dict(page='back', tables=[back])],
                     [dict(key='duplex', values=dict(nome='Pessoa Sintética', identificacao='ID-TESTE-001',
                                                    campo_verso='Somente no verso', observacao_verso=''))],
                     {'duplex': {'verso-r2c2': 'Somente no verso', 'verso-r3c2': 'Observação: '}},
                     ['Troca de página', 'União de campos', 'Copiar tabela independente',
                      'Frente/verso em PDF e imagem', 'Recuperar texto em edição'])
    return (boletim, escala, merged, duplex)


def validate_fixture(value):
    assert value['runtime_model'] is False
    assert value['fixture_format'] == 'fornax-table-acceptance-spec'
    assert 'schema_version' not in value
    identifiers = set()
    for page in value['pages']:
        for table in page['tables']:
            assert len(table['column_widths_mm']) == table['columns']
            assert len(table['row_heights_mm']) == table['rows']
            assert all(size > 0 for size in table['column_widths_mm'] + table['row_heights_mm'])
            occupied = set()
            for item in table['cells']:
                assert item['key'] not in identifiers
                identifiers.add(item['key'])
                area = {(r, c) for r in range(item['row'], item['row'] + item['row_span'])
                        for c in range(item['column'], item['column'] + item['column_span'])}
                assert area and not occupied.intersection(area)
                assert all(0 <= r < table['rows'] and 0 <= c < table['columns'] for r, c in area)
                occupied.update(area)
            assert len(occupied) == table['rows'] * table['columns']
    record_ids = {record['key'] for record in value['records']}
    for record, expectations in value['expected_resolved_text'].items():
        assert record in record_ids
        assert set(expectations).issubset(identifiers)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'tests/fixtures/tables')
    parser.add_argument('--check', action='store_true', help='Confere os arquivos sem regravá-los.')
    args = parser.parse_args()
    if not args.check:
        args.output.mkdir(parents=True, exist_ok=True)
    for value in cases():
        validate_fixture(value)
        target = args.output / (value['id'] + '.json')
        content = json.dumps(value, ensure_ascii=False, indent=2) + '\n'
        if args.check:
            assert target.read_text(encoding='utf-8') == content, target
        else:
            target.write_text(content, encoding='utf-8')
        print(target.name, sha256(content.encode()).hexdigest(), flush=True)


if __name__ == '__main__':
    main()
