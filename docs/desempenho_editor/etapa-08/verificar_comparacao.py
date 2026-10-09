"""Compara conteúdos e métricas, sem confundir UUIDs/nonce com alterações visuais."""
from pathlib import Path
import json
import hashlib
import difflib
import subprocess
from tempfile import TemporaryDirectory

ROOT=Path(__file__).resolve().parents[3]
OUT=Path(__file__).resolve().parent
REFERENCE=Path('/tmp/fornax-etapa08-reference')


def main():
    before=json.loads((OUT/'antes.json').read_text())['results']
    after=json.loads((OUT/'depois.json').read_text())['results']
    eb=json.loads((OUT/'ambiente-antes.json').read_text());ea=json.loads((OUT/'ambiente-depois.json').read_text())
    assert eb['harness_sha256']==ea['harness_sha256']
    for field in ('python','pyside6','qt','platform','qt_platform','theme','window_requested','warmups','warm_samples','cold_samples'):
        assert eb[field]==ea[field],field
    allowed={'core/fornax_container.py','core/fornax_session.py','features/editor/editor_window.py','features/editor/recovery_worker.py'}
    changes={name for name in set(eb['product_sha256'])|set(ea['product_sha256']) if eb['product_sha256'].get(name)!=ea['product_sha256'].get(name)}
    assert changes==allowed,changes
    rows=[]
    for b,a in zip(before,after):
        assert b['scenario']==a['scenario'] and b['input_sha256']==a['input_sha256']
        assert b['status']==a['status']=='ok'
        assert b['font']==a['font'] and b['viewport']==a['viewport']
        assert len(b['states'])==len(a['states'])==20
        for old,new in zip(b['states'],a['states']):
            assert {k:v for k,v in old.items() if k!='rss_bytes'}=={k:v for k,v in new.items() if k!='rss_bytes'}, b['scenario']['id']
        expected=1 if not a['scenario']['continuous'] else a['scenario']['repeats']
        assert set(a['writes'])=={expected}
        assert set(b['writes'])=={b['scenario']['repeats']}
        rows.append({'case':b['scenario']['id'],'before_total':b['summary'],'after_total':a['summary'],
          'before_call':b['call_summary'],'after_call':a['call_summary'],
          'before_ui_gap':b['ui_gap_summary'],'after_ui_gap':a['ui_gap_summary'],
          'before_writes':b['writes'][0],'after_writes':a['writes'][0],
          'before_max_rss_mib':max(s['rss_bytes'] for s in b['states'])/1024**2,
          'after_max_rss_mib':max(s['rss_bytes'] for s in a['states'])/1024**2})
    assert len(rows)==8
    result={'cases':rows,'matched_samples':160,'harness_unchanged':True,'source_changes':sorted(changes),
            'logical_states_and_pixels_exact':True,'asset_filenames_normalized_by_sha256':True,
            'asset_multiplicity_preserved':True,'rss_is_current_after_completion_not_peak':True}
    (OUT/'verificacao-comparacao.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n')
    patch=[]
    for name in sorted(allowed):
        old=REFERENCE/Path(name).name
        exists=name!='features/editor/recovery_worker.py'
        previous=old.read_text() if exists else ''
        current=(ROOT/name).read_text()
        patch.append(f'diff --git a/{name} b/{name}\n')
        patch.extend(difflib.unified_diff(previous.splitlines(keepends=True),current.splitlines(keepends=True),fromfile='a/'+name if exists else '/dev/null',tofile='b/'+name))
    patch_path=OUT/'alteracoes-etapa-08.patch';patch_path.write_text(''.join(patch))
    with TemporaryDirectory(prefix='fornax-stage08-reverse-') as temporary:
        folder=Path(temporary)
        for name in allowed:
            target=folder/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes((ROOT/name).read_bytes())
        completed=subprocess.run(['patch','--reverse','--batch','-p1','--input',str(patch_path)],cwd=folder,capture_output=True,text=True)
        assert completed.returncode==0,completed.stdout+completed.stderr
        for name in allowed-{'features/editor/recovery_worker.py'}:
            assert (folder/name).read_bytes()==(REFERENCE/Path(name).name).read_bytes(),name
        assert not (folder/'features/editor/recovery_worker.py').exists()
    assert all(hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==value for name,value in ea['product_sha256'].items())
    audit={'reverse_patch_exact':True,'only_expected_product_changes':True,
           'final_hashes_match_measurement':True,'source_reference_sha256':{name:eb['product_sha256'].get(name) for name in sorted(allowed)},
           'source_current_sha256':{name:ea['product_sha256'][name] for name in sorted(allowed)}}
    (OUT/'verificacao-patch.json').write_text(json.dumps(audit,indent=2)+'\n')
    print('160 pares de estados idênticos; hashes e reversão de quatro arquivos conferidos.')

if __name__=='__main__':main()
