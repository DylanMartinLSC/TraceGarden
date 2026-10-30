import json
from fastapi.testclient import TestClient
from tracegarden.app import app
from test_core import fixture_image

client=TestClient(app)


def test_home_and_assets():
    for path in ['/','/static/app.js','/static/style.css']:
        r=client.get(path); assert r.status_code==200
        assert r.headers['X-Content-Type-Options']=='nosniff'


def test_roundtrip():
    r=client.post('/api/trace',files={'file':('test.png',fixture_image(),'image/png')})
    assert r.status_code==200
    svg=r.json()['svg']
    for fmt in ['svg','pdf','eps','dxf']:
        r=client.post('/api/export',json={'svg':svg,'format':fmt})
        assert r.status_code==200 and len(r.content)>100


def test_validation():
    for opts in ['{',json.dumps({'colors':-1}),json.dumps({'preset':'missing'})]:
        assert client.post('/api/trace',files={'file':('a',fixture_image())},data={'options':opts}).status_code==400
    assert client.post('/api/trace',files={'file':('a',b'bad')}).status_code==400
    assert client.post('/api/export',json={'svg':'bad','format':'pdf'}).status_code==400


def test_origin_and_host():
    assert client.post('/api/trace',headers={'origin':'https://evil.example'}).status_code==403
    assert client.get('/',headers={'host':'evil.example'}).status_code==400


def test_batch_zip_and_safe_names():
    import io,zipfile
    svg=client.post('/api/trace',files={'file':('a.png',fixture_image())}).json()['svg']
    r=client.post('/api/export-batch',json={'items':[{'svg':svg,'format':'svg'}]*2,'names':['../../escape','same']})
    assert r.status_code==200
    archive=zipfile.ZipFile(io.BytesIO(r.content))
    assert len(archive.namelist())==2
    assert all('/' not in name and '\\' not in name for name in archive.namelist())
    assert client.post('/api/export-batch',json={'items':[],'names':[]}).status_code==400
