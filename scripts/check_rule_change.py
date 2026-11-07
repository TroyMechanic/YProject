"""CI guard: rule changes need prose, a decision record and a version bump."""
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY = 'backend/app/services/rule_policy.py'
RULE_FILES = {
    POLICY, 'backend/app/services/chan_analyzer.py',
    'backend/app/services/segment_analyzer.py', 'backend/app/services/central_zone_analyzer.py',
    'backend/app/models/schemas.py', 'backend/app/services/csv_store.py',
    'backend/app/services/chart_service.py', 'frontend/src/components/KLineChart.tsx',
    'backend/app/services/recursive_analyzer.py', 'backend/app/services/hierarchy_service.py',
    'frontend/src/components/HierarchyPanel.tsx', 'backend/app/services/market_data_service.py', 'backend/app/services/research_analyzer.py', 'frontend/src/utils/analysisLabels.ts',
    'frontend/src/utils/chartTimeline.ts', 'frontend/src/utils/rangeNavigation.ts', 'frontend/src/utils/wheelNavigation.ts',
}


def git(*args):
    return subprocess.run(['git', *args], cwd=ROOT, text=True, capture_output=True, check=True).stdout


def main():
    base = os.environ.get('RULE_BASE') or (sys.argv[1] if len(sys.argv) > 1 else 'HEAD')
    if not base or set(base) == {'0'}:
        print('Initial repository push: baseline tests still apply.')
        return 0
    changed = set(git('diff', '--name-only', base).splitlines())
    # Include newly added, not yet tracked files for local use.
    changed.update(git('ls-files', '--others', '--exclude-standard').splitlines())
    if not changed & RULE_FILES:
        print('No guarded rule/serialization files changed.')
        return 0
    errors = []
    if 'docs/chan-rules.md' not in changed:
        errors.append('Update docs/chan-rules.md with the actual final behavior.')
    if not any(name.startswith('docs/decisions/') and name.endswith('.md') for name in changed):
        errors.append('Add/update a docs/decisions/ rule decision with impact and verification.')
    old = subprocess.run(['git', 'show', f'{base}:{POLICY}'], cwd=ROOT, text=True, capture_output=True)
    if old.returncode == 0:
        pattern = r'RULE_VERSION\s*=\s*"([^"]+)"'
        before = re.search(pattern, old.stdout)
        after = re.search(pattern, (ROOT / POLICY).read_text())
        if not before or not after or before.group(1) == after.group(1):
            errors.append('Bump RULE_VERSION; update the hand-checked baseline version after review.')
    if errors:
        print('\n'.join(errors), file=sys.stderr)
        return 1
    print('Rule documentation, decision record and version checks passed.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
