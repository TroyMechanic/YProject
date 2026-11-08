import json
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from app.api import routes
from app.models.schemas import Kline, KlinePeriod, RecalculateRequest, RuleProfile, SyncRequest
from app.services.chart_service import AnalysisStateError, ChartService
from app.services.csv_store import CsvStore
from app.services.rule_policy import digest, input_hash
from test_rule_contracts import bars


@pytest.fixture
def service(tmp_path):
    store = CsvStore(tmp_path / 'raw', tmp_path / 'analyzed')
    store.upsert_klines('DEMO', KlinePeriod.DAILY, bars([(10,7),(12,9),(11,8),(9,6),(8,4),(10,6),(12,8),(13,10),(11,9)]))
    return ChartService(store)


def test_date_window_does_not_replace_full_history_analysis(service, monkeypatch):
    monkeypatch.setattr(routes, 'chart_service', service)
    before = service.recalculate('DEMO', KlinePeriod.DAILY)
    response = routes.recalculate('DEMO', RecalculateRequest(startDate='2024-01-05', endDate='2024-01-06'))
    whole = service.get_chart('DEMO', KlinePeriod.DAILY, None, None)
    view = service.get_chart('DEMO', KlinePeriod.DAILY, date(2024,1,5), date(2024,1,6))
    assert whole.bis == before.bis and len(whole.klines) == 9
    assert response['analysis']['sourceCount'] == 9
    assert len(view.klines) == 2 and view.analysis.run_id == whole.analysis.run_id
    assert len(service.store.load_klines('DEMO', KlinePeriod.DAILY)) == 9


def test_sync_keeps_saved_parameters_and_empty_fetch_keeps_run(service, monkeypatch):
    before = service.recalculate('DEMO', KlinePeriod.DAILY, 6, RuleProfile.SEPARATED)
    monkeypatch.setattr(service.market_data, 'fetch', lambda *args: bars([(10,7)]))
    service.sync('DEMO', KlinePeriod.DAILY, None, None)
    after = service.get_chart('DEMO', KlinePeriod.DAILY, None, None)
    assert after.analysis.settings == before.analysis.settings
    assert after.analysis.effective_min_kline_gap == 6
    monkeypatch.setattr(service.market_data, 'fetch', lambda *args: [])
    assert service.sync('DEMO', KlinePeriod.DAILY, None, None) == 0
    assert service.get_chart('DEMO', KlinePeriod.DAILY, None, None).analysis.run_id == after.analysis.run_id


def test_unmodified_query_reuses_batch_and_raw_update_invalidates_it(service):
    first = service.get_chart('DEMO', KlinePeriod.DAILY, None, None)
    assert service.get_chart('DEMO', KlinePeriod.DAILY, None, None).analysis.run_id == first.analysis.run_id
    source = bars([(10,7)])[0].model_copy(update={'time': date(2024,1,10)})
    service.store.upsert_klines('DEMO', KlinePeriod.DAILY, [source])
    second = service.get_chart('DEMO', KlinePeriod.DAILY, None, None)
    assert second.analysis.run_id != first.analysis.run_id
    assert second.analysis.input_hash != first.analysis.input_hash
    assert second.analysis.source_count == 10


def test_engine_change_rebuilds_without_losing_profile(service, monkeypatch):
    before = service.recalculate('DEMO', KlinePeriod.DAILY, 5, RuleProfile.SEPARATED)
    monkeypatch.setattr('app.services.chart_service.engine_hash', lambda: 'new-engine')
    after = service.get_chart('DEMO', KlinePeriod.DAILY, None, None)
    assert after.analysis.run_id != before.analysis.run_id
    assert after.analysis.engine_hash == 'new-engine'
    assert after.analysis.settings == before.analysis.settings


def test_rule_catalog_change_invalidates_saved_result(service, monkeypatch):
    before = service.recalculate('DEMO', KlinePeriod.DAILY)
    from app.services.rule_policy import PRINCIPLES
    monkeypatch.setitem(PRINCIPLES, 'K01', '测试规则目录变更')
    after = service.get_chart('DEMO', KlinePeriod.DAILY, None, None)
    assert after.analysis.run_id != before.analysis.run_id
    assert after.analysis.rule_hash != before.analysis.rule_hash
    assert service.get_chart('DEMO', KlinePeriod.DAILY, None, None).analysis.run_id == after.analysis.run_id


def test_archives_hold_complete_inputs_and_rules_for_each_run(service):
    first = service.recalculate('DEMO', KlinePeriod.DAILY, 1)
    second = service.recalculate('DEMO', KlinePeriod.DAILY, 5, RuleProfile.SEPARATED)
    archive = service.store.analyzed_dir / 'runs' / 'DEMO_daily'
    for chart in [first,second]:
        stored = json.loads((archive / f'{chart.analysis.run_id}.json').read_text())
        assert len(stored['klines']) == 9
        assert stored['analysis']['ruleCatalog']['principles']
        assert stored['analysis']['resultHash'] == digest({key:value for key,value in stored.items() if key != 'analysis'})
    assert service.get_chart('DEMO', KlinePeriod.DAILY, None, None).analysis.run_id == second.analysis.run_id


def test_partial_export_failure_never_publishes_mixed_api_result(service, monkeypatch):
    before = service.recalculate('DEMO', KlinePeriod.DAILY)
    def fail(*args):
        raise OSError('模拟写盘失败')
    monkeypatch.setattr(service.store, 'save_segments', fail)
    with pytest.raises(OSError):
        service.recalculate('DEMO', KlinePeriod.DAILY, 5, RuleProfile.SEPARATED)
    after = service.get_chart('DEMO', KlinePeriod.DAILY, None, None)
    assert after.analysis.run_id == before.analysis.run_id
    assert after.bis == before.bis


def test_corrupt_snapshot_is_not_silently_relabelled(service):
    service.recalculate('DEMO', KlinePeriod.DAILY)
    path = service.store._analysis_path('DEMO', KlinePeriod.DAILY)
    saved = json.loads(path.read_text())
    saved['bis'][0]['endPrice'] = 999
    path.write_text(json.dumps(saved))
    with pytest.raises(AnalysisStateError, match='校验失败'):
        service.get_chart('DEMO', KlinePeriod.DAILY, None, None)
    path.write_text('{broken')
    with pytest.raises(AnalysisStateError, match='损坏'):
        service.recalculate('DEMO', KlinePeriod.DAILY)


def test_periods_and_profiles_are_isolated(service):
    daily = service.recalculate('DEMO', KlinePeriod.DAILY, 5, RuleProfile.SEPARATED)
    weekly = service.recalculate('DEMO', KlinePeriod.WEEKLY)
    assert weekly.analysis.settings.rule_profile == RuleProfile.LEGACY
    assert weekly.analysis.source_count == 0
    assert service.get_chart('DEMO', KlinePeriod.DAILY, None, None).analysis.run_id == daily.analysis.run_id


def test_intraday_snapshot_and_date_filter_keep_full_datetime(service):
    rows = [Kline(time=datetime(2024,1,1,10,30)+timedelta(minutes=i), open=10,high=12,low=9,close=11) for i in range(3)]
    service.store.upsert_klines('DEMO', KlinePeriod.MINUTE_1, rows)
    whole = service.recalculate('DEMO', KlinePeriod.MINUTE_1)
    view = service.get_chart('DEMO', KlinePeriod.MINUTE_1, date(2024,1,1),date(2024,1,1))
    assert [k.time for k in view.klines] == [k.time for k in rows]
    assert view.analysis.source_end == rows[-1].time
    assert view.analysis.input_hash == input_hash(rows)
    assert view.analysis.run_id == whole.analysis.run_id


def test_serialized_concurrent_writes_publish_one_consistent_snapshot(service):
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(lambda gap: service.recalculate('DEMO',KlinePeriod.DAILY,gap), [1,4,6,2]))
    final = service.get_chart('DEMO', KlinePeriod.DAILY,None,None)
    assert final.analysis.run_id in {chart.analysis.run_id for chart in results}
    expected = next(chart for chart in results if chart.analysis.run_id == final.analysis.run_id)
    assert final == expected


def test_legacy_csv_without_metadata_is_rebuilt_from_raw(service):
    old = service.analyzer.analyze(service.store.load_klines('DEMO', KlinePeriod.DAILY), 5)
    service.store.save_bis('DEMO', KlinePeriod.DAILY, old[1])
    chart = service.get_chart('DEMO', KlinePeriod.DAILY,None,None)
    assert chart.analysis.settings.min_kline_gap == 1
    assert len(chart.bis) == 1
    assert chart.analysis.rule_catalog['version'] == chart.analysis.rule_version


def test_recorded_rule_catalog_tampering_is_detected(service):
    service.recalculate('DEMO',KlinePeriod.DAILY)
    path = service.store._analysis_path('DEMO',KlinePeriod.DAILY)
    saved=json.loads(path.read_text())
    saved['analysis']['ruleCatalog']['principles'][0]['text']='错误标注'
    path.write_text(json.dumps(saved))
    with pytest.raises(AnalysisStateError,match='溯源校验失败'):
        service.get_chart('DEMO',KlinePeriod.DAILY,None,None)


def test_compare_tool_reports_same_input_profile_differences(service):
    import importlib.util
    script=Path(__file__).resolve().parents[2] / 'scripts/compare_analysis.py'
    spec=importlib.util.spec_from_file_location('analysis_compare',script)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    first=service.recalculate('DEMO',KlinePeriod.DAILY,1,RuleProfile.LEGACY)
    second=service.recalculate('DEMO',KlinePeriod.DAILY,1,RuleProfile.SEPARATED)
    archive=service.store.analyzed_dir / 'runs/DEMO_daily'
    report=module.compare(module.load(archive/f'{first.analysis.run_id}.json'),module.load(archive/f'{second.analysis.run_id}.json'))
    assert report['sameInput'] and report['sameEngine']
    assert report['changes']['bis']['beforeCount']==1
    assert report['changes']['bis']['afterCount']==0
    assert len(report['changes']['bis']['removed'])==1


def test_v2_snapshot_migration_checks_original_shape_and_preserves_settings(service):
    chart=service.recalculate('DEMO',KlinePeriod.DAILY,5,RuleProfile.SEPARATED)
    payload=chart.model_dump(mode='json',by_alias=True)
    for item in payload['fractals']: item.pop('strength',None)
    for item in payload['bis']:
        item.pop('momentum',None);item.pop('confirmedAt',None)
    metadata=payload['analysis']
    metadata['settings']={'ruleProfile':'separated','minKlineGap':5}
    metadata['ruleVersion']='2.0.0'
    metadata['ruleCatalog']['version']='2.0.0'
    metadata['ruleCatalog']['principles']=metadata['ruleCatalog']['principles'][:11]
    metadata['principleIds']=[p['id'] for p in metadata['ruleCatalog']['principles']]
    metadata['ruleHash']=digest({'catalog':metadata['ruleCatalog'],'settings':{'rule_profile':'separated','min_kline_gap':5},'gap':5})
    metadata['resultHash']=digest({k:v for k,v in payload.items() if k!='analysis'})
    service.store._analysis_path('DEMO',KlinePeriod.DAILY).write_text(json.dumps(payload))
    migrated=service.get_chart('DEMO',KlinePeriod.DAILY,None,None)
    assert migrated.analysis.rule_version=='5.1.0' and migrated.analysis.run_id!=chart.analysis.run_id
    assert migrated.analysis.settings.rule_profile==RuleProfile.SEPARATED
    assert migrated.analysis.settings.min_kline_gap==5
    assert 'indicators' not in migrated.model_dump()
