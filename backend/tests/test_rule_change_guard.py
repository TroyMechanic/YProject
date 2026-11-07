import importlib.util
import subprocess
from pathlib import Path


def test_ci_guard_rejects_missing_docs_decision_or_version(tmp_path,monkeypatch,capsys):
    script=Path(__file__).resolve().parents[2]/'scripts/check_rule_change.py'
    spec=importlib.util.spec_from_file_location('rule_change_guard',script)
    guard=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard)
    monkeypatch.setattr(guard,'ROOT',tmp_path)
    monkeypatch.setenv('RULE_BASE','HEAD')

    def git(*args):
        subprocess.run(['git',*args],cwd=tmp_path,check=True,capture_output=True)

    policy=tmp_path/guard.POLICY
    policy.parent.mkdir(parents=True)
    policy.write_text('RULE_VERSION = "1.0.0"\n')
    document=tmp_path/'docs/chan-rules.md'
    document.parent.mkdir()
    document.write_text('原规则\n')
    git('init')
    git('add','.')
    git('-c','user.name=Test','-c','user.email=test@example.invalid','commit','-m','baseline')
    policy.write_text('RULE_VERSION = "1.0.0"\n# rule changed\n')
    assert guard.main()==1
    errors=capsys.readouterr().err
    assert 'chan-rules' in errors and 'decisions' in errors and 'RULE_VERSION' in errors
    document.write_text('明确新规则\n')
    decisions=tmp_path/'docs/decisions'
    decisions.mkdir()
    (decisions/'0002-change.md').write_text('选择、影响及验证\n')
    assert guard.main()==1
    assert 'RULE_VERSION' in capsys.readouterr().err
    policy.write_text('RULE_VERSION = "2.0.0"\n# rule changed\n')
    assert guard.main()==0
