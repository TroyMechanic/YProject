"""Exercise FastAPI's ASGI request/validation/serialization without an HTTP test dependency."""
import asyncio
import json
from datetime import date
from urllib.parse import urlsplit

import pytest

from app.api import routes
from app.main import app
from app.models.schemas import KlinePeriod
from app.services.chart_service import ChartService
from app.services.csv_store import CsvStore
from test_rule_contracts import bars


async def request(method, target, payload=None):
    url = urlsplit(target)
    body = json.dumps(payload).encode() if payload is not None else b''
    messages = []
    delivered = False

    async def receive():
        nonlocal delivered
        if not delivered:
            delivered = True
            return {'type':'http.request', 'body':body, 'more_body':False}
        await asyncio.Event().wait()

    async def send(message):
        messages.append(message)

    scope = {'type':'http','asgi':{'version':'3.0'}, 'http_version':'1.1', 'method':method,
             'scheme':'http', 'path':url.path, 'raw_path':url.path.encode(),
             'query_string':url.query.encode(), 'root_path':'', 'server':('test',80),
             'client':('127.0.0.1',1234), 'headers':[(b'content-type',b'application/json')]}
    await app(scope,receive,send)
    status = next(m['status'] for m in messages if m['type']=='http.response.start')
    raw = b''.join(m.get('body',b'') for m in messages if m['type']=='http.response.body')
    return status, json.loads(raw)


@pytest.fixture
def api_service(tmp_path,monkeypatch):
    service = ChartService(CsvStore(tmp_path/'raw',tmp_path/'analyzed'))
    source = bars([(10,7),(12,9),(11,8),(9,6),(8,4),(10,6),(12,8),(13,10),(11,9)])
    monkeypatch.setattr(service.market_data,'fetch',lambda *args:source)
    monkeypatch.setattr(routes,'chart_service',service)
    return service


def test_http_rules_sync_chart_recalculate_and_saved_parameters(api_service):
    status,catalog=asyncio.run(request('GET','/api/chan/rules'))
    assert status==200 and catalog['recommendedProfile']=='separated'
    status,_=asyncio.run(request('POST','/api/stocks/DEMO/sync',{'period':'daily','minKlineGap':5,'ruleProfile':'separated'}))
    assert status==200
    status,chart=asyncio.run(request('GET','/api/stocks/DEMO/chart?startDate=2024-01-05&endDate=2024-01-06'))
    assert status==200 and len(chart['klines'])==2
    assert chart['analysis']['sourceCount']==9 and chart['analysis']['effectiveMinKlineGap']==5
    status,result=asyncio.run(request('POST','/api/stocks/DEMO/chan/recalculate',{'startDate':'2024-01-05','endDate':'2024-01-06','minKlineGap':1,'ruleProfile':'legacy'}))
    assert status==200 and result['biCount']==1 and result['analysis']['sourceCount']==9
    status,_=asyncio.run(request('POST','/api/stocks/DEMO/sync',{'period':'daily'}))
    assert status==200
    status,whole=asyncio.run(request('GET','/api/stocks/DEMO/chart'))
    assert status==200 and len(whole['bis'])==1 and whole['analysis']['settings']['ruleProfile']=='legacy'


@pytest.mark.parametrize('payload',[
    {'ruleProfile':'mystery'}, {'minKlineGap':21}, {'minKlineGap':1.5}, {'minKlineGap':True},
    {'minKlineGapp':5}, {'startDate':'2024-02-01','endDate':'2024-01-01'},
])
def test_http_rejects_invalid_or_misspelled_rules(api_service,payload):
    status,result=asyncio.run(request('POST','/api/stocks/DEMO/chan/recalculate',payload))
    assert status==422 and result['detail']
    assert api_service.store.load_analysis('DEMO',KlinePeriod.DAILY) is None


def test_http_corrupt_snapshot_conflict_and_invalid_query(api_service):
    api_service.recalculate('DEMO',KlinePeriod.DAILY)
    path=api_service.store._analysis_path('DEMO',KlinePeriod.DAILY)
    path.write_text('{bad')
    status,result=asyncio.run(request('GET','/api/stocks/DEMO/chart'))
    assert status==409 and '损坏' in result['detail']
    status,_=asyncio.run(request('GET','/api/stocks/DEMO/chart?startDate=2024-02-01&endDate=2024-01-01'))
    assert status==422


def test_recursive_http_distinct_base_display_validation_and_saved_depth(api_service):
    status,chart=asyncio.run(request('GET','/api/stocks/002475/structure/chart?period=daily&basePeriod=minute5&maxLevel=3'))
    assert status==200 and chart['period']=='daily' and chart['hierarchy']['basePeriod']=='minute5'
    assert chart['hierarchy']['maxLevel']==3 and chart['hierarchy']['layers']==[]
    status,again=asyncio.run(request('GET','/api/stocks/002475/structure/chart?period=daily'))
    assert status==200 and again['hierarchy']['maxLevel']==3
    status,_=asyncio.run(request('GET','/api/stocks/002475/structure/chart?basePeriod=daily'))
    assert status==422
    status,_=asyncio.run(request('GET','/api/stocks/002475/structure/chart?maxLevel=9'))
    assert status==422
    status,result=asyncio.run(request('POST','/api/stocks/002475/structure/sync',{'period':'daily','basePeriod':'minute5','maxLevel':2,'divergenceRatio':.6}))
    assert status==200 and result['hierarchy']['baseAnalysis']['settings']['divergenceRatio']==.6
    assert result['hierarchy']['baseAnalysis']['sourceCount']==9
