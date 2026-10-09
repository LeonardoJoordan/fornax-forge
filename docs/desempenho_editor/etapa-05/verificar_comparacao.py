"""Audita as evidências da etapa 05 sem executar novamente os benchmarks."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
CHANGED = {
    "features/editor/editor_window.py",
    "features/editor/organogram_editor.py",
    "features/editor/controls.py",
}


def read(name):
    return json.loads((OUT / name).read_text())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    before_env, after_env = read("ambiente-antes.json"), read("ambiente-depois.json")
    assert before_env["harness_sha256"] == after_env["harness_sha256"]
    for name, expected in after_env["harness_sha256"].items():
        assert digest(ROOT / "tests/performance" / name) == expected, name
    environment_keys = (
        "platform", "python", "cpu_model", "pyside6", "qt", "qt_platform",
        "theme", "locale", "window_requested", "workers_concurrent", "warmups",
        "warm_samples", "rss_limit_bytes",
    )
    for name in environment_keys:
        assert before_env[name] == after_env[name], name

    product_changed = {
        name for name, value in before_env["product_sha256"].items()
        if after_env["product_sha256"].get(name) != value
    }
    assert product_changed == CHANGED, product_changed
    whitespace = OUT / "ajuste-espacos.patch"
    with tempfile.TemporaryDirectory(prefix="fornax-copy-audit-") as directory:
        restored = Path(directory)
        for name in CHANGED:
            target = restored / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, target)
        subprocess.run(
            ["patch", "-p1", "-R", "--batch", "--directory", directory,
             "--input", str(OUT / "alteracoes-etapa-05.patch")],
            check=True, capture_output=True,
        )
        recovered = {name: digest(restored / name) for name in sorted(CHANGED)}
        assert all(value == before_env["product_sha256"][name]
                   for name, value in recovered.items())

        if whitespace.exists():
            name = "features/editor/editor_window.py"
            shutil.copyfile(ROOT / name, restored / name)
            subprocess.run(
                ["patch", "-p1", "-R", "--batch", "--directory", directory,
                 "--input", str(whitespace)], check=True, capture_output=True,
            )
            assert digest(restored / name) == after_env["product_sha256"][name]
            final_lines = (ROOT / name).read_text().splitlines()
            timed_lines = (restored / name).read_text().splitlines()
            assert [line.rstrip() for line in final_lines] == [line.rstrip() for line in timed_lines]

    for name, expected in after_env["product_sha256"].items():
        if name == "features/editor/editor_window.py" and whitespace.exists():
            continue
        assert digest(ROOT / name) == expected, name
    additional = read("contratos-adicionais-depois.json")
    contracts = read("contratos-antes.json")
    for name, value in contracts.items():
        if name == "tests/test_editor_copy_insertion.py":
            value = additional["test_editor_copy_insertion.py"]
        assert digest(ROOT / name) == value, name
    for name, value in read("probe-antes.json").items():
        assert digest(ROOT / name) == value, name

    before = {r["scenario"]["id"]: r for r in read("antes.json")["results"]}
    after = {r["scenario"]["id"]: r for r in read("depois.json")["results"]}
    assert len(before) == len(after) == 14 and before.keys() == after.keys()
    fields = (
        "final_document_sha256", "scene_items", "selected_items", "operation_index",
        "history_index", "visual_cache_bytes", "layer_rows", "clipboard_sha256",
    )
    rows = []
    for name, old in before.items():
        new = after[name]
        assert old["status"] == new["status"] == "ok", name
        for field in ("input_sha256", "scenario", "viewport", "ui_font", "completion"):
            assert old[field] == new[field], (name, field)
        assert len(old["samples_ms"]) == len(new["samples_ms"]) == 20
        assert len(old["memory_and_structure"]) == len(new["memory_and_structure"]) == 20
        for a, b in zip(old["memory_and_structure"], new["memory_and_structure"]):
            assert all(a[field] == b[field] for field in fields), name
        a, b = old["summary"]["median_ms"], new["summary"]["median_ms"]
        rows.append({"scenario": name, "before": old["summary"], "after": new["summary"],
                     "median_reduction_percent": (1 - b / a) * 100,
                     "retained_before": old["memory_and_structure"][0]["original_items_retained"],
                     "retained_after": new["memory_and_structure"][0]["original_items_retained"]})
    states = {}
    for theme in ("dark", "light"):
        old, new = read(f"evidencia-antes-{theme}.json"), read(f"evidencia-depois-{theme}.json")
        assert old == new and len(old) == 21, theme
        states[theme] = len(old)
    result = {
        "all_checks_passed": True, "scenarios": 14, "samples_per_version": 280,
        "identical_fields_per_sample": list(fields), "states_per_theme": states,
        "environment_fields_identical": list(environment_keys), "timing_instruments_identical": True,
        "product_changed": sorted(product_changed),
        "post_measurement_change": "Somente espaços em quatro linhas vazias; patch reversível verificado." if whitespace.exists() else None,
        "additional_contract": additional, "results": rows,
        "final_product_sha256": {name: digest(ROOT / name) for name in sorted(CHANGED)},
    }
    (OUT / "verificacao-comparacao.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    (OUT / "verificacao-patch.json").write_text(json.dumps({"all_recovered_hashes_match": True, "recovered_sha256": recovered}, indent=2) + "\n")
    print("14 cenários, 280 amostras por versão, 42 estados e hashes conferidos.")


if __name__ == "__main__":
    main()
