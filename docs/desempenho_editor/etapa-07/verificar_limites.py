"""Contratos suplementares: orçamento efetivo, passos, JSON e estados mutáveis."""
import argparse
from copy import deepcopy
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[3]
RECORDS = {}
HistoryManager = None


def record(history, name):
    RECORDS[name] = {
        'states': deepcopy(history._undo_stack), 'index': history._current_index,
        'sizes': list(history._state_sizes), 'undo': history.can_undo(),
        'redo': history.can_redo(),
    }


class LimitsTest(unittest.TestCase):
    def test_unicode_budget_actually_evicts_and_retains_one_oversized_state(self):
        history = HistoryManager(max_steps=30, max_bytes=40)
        for value in ('ação', 'coração', 'instituição'):
            history.push({'value': value})
        self.assertEqual(history._undo_stack, [{'value': 'instituição'}])
        self.assertEqual(history._current_index, 0)
        self.assertLessEqual(sum(history._state_sizes), 40)
        self.assertFalse(history.can_undo())
        oversized = {'value': 'á' * 50}
        history.push(oversized)
        self.assertEqual(history._undo_stack, [oversized])
        self.assertEqual(history._current_index, 0)
        self.assertGreater(history._state_sizes[0], 40)
        self.assertEqual(history._state_sizes, [len(json.dumps(oversized, sort_keys=True, ensure_ascii=False).encode('utf-8'))])
        record(history, 'unicode-budget')

    def test_step_eviction_undo_redo_and_new_branch_preserve_signals(self):
        history = HistoryManager(max_steps=3, max_bytes=500)
        signals = []
        history.canUndoChanged.connect(lambda value: signals.append(('undo', value)))
        history.canRedoChanged.connect(lambda value: signals.append(('redo', value)))
        for value in range(6):
            history.push({'value': value})
        self.assertEqual(history._undo_stack, [{'value': 3}, {'value': 4}, {'value': 5}])
        self.assertEqual(history.undo(), {'value': 4})
        self.assertEqual(history.redo(), {'value': 5})
        history.undo()
        history.push({'value': 99})
        self.assertEqual(history._undo_stack, [{'value': 3}, {'value': 4}, {'value': 99}])
        self.assertFalse(history.can_redo())
        self.assertEqual(signals[-2:], [('undo', True), ('redo', False)])
        record(history, 'steps-and-branch')
        RECORDS['steps-and-branch']['signals'] = signals

    def test_json_distinguishes_int_float_bool_and_literal_unicode_escape(self):
        history = HistoryManager(max_steps=20)
        for value in (1, 1.0, True, 'ç', r'\u00e7'):
            history.push({'value': value})
        self.assertEqual(len(history._undo_stack), 5)
        history.push({'value': r'\u00e7'})
        self.assertEqual(len(history._undo_stack), 5)
        record(history, 'json-equivalence')

    def test_mutated_current_state_is_compared_again_without_stale_json(self):
        history = HistoryManager(max_steps=20)
        history.push({'path': 'asset:antes.png'})
        history.push({'path': 'asset:outro.png'})
        history.undo()
        history._undo_stack[0]['path'] = 'asset:salvo.png'
        history.push({'path': 'asset:salvo.png'})
        self.assertEqual(len(history._undo_stack), 2)
        self.assertTrue(history.can_redo())
        history.push({'path': 'asset:antes.png'})
        self.assertEqual(history._undo_stack, [{'path': 'asset:salvo.png'}, {'path': 'asset:antes.png'}])
        self.assertFalse(history.can_redo())
        record(history, 'mutable-state')


def main():
    global HistoryManager
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=ROOT/'core/history_manager.py')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    from PySide6.QtCore import QCoreApplication
    app = QCoreApplication([])
    spec = importlib.util.spec_from_file_location('_fornax_history_under_test', args.source)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    HistoryManager = module.HistoryManager
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(LimitsTest))
    args.output.write_text(json.dumps({
        'source_sha256': sha256(args.source.read_bytes()).hexdigest(),
        'probe_sha256': sha256(Path(__file__).read_bytes()).hexdigest(),
        'tests': result.testsRun, 'passed': result.wasSuccessful(), 'records': RECORDS,
    }, ensure_ascii=False, indent=2)+'\n')
    return int(not result.wasSuccessful())


if __name__ == '__main__':
    raise SystemExit(main())
