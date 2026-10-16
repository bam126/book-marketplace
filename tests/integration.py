"""Real Docker/HTTP checks. Run from project root; temporarily stops lab containers."""
import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'artifacts'
DOCKER = shutil.which('docker') or str(Path(os.environ.get('LOCALAPPDATA', '')) / 'Programs/DockerDesktop/resources/bin/docker.exe')
GATEWAY = 'http://127.0.0.1:8080'
CONSUL = 'http://127.0.0.1:8500'
EVENTS = []


def record(event, **data):
    row = {'time': datetime.now(timezone.utc).isoformat(), 'event': event, **data}
    EVENTS.append(row)
    print(json.dumps(row, ensure_ascii=True), flush=True)


def docker(*args):
    result = subprocess.run([DOCKER, *args], cwd=ROOT, capture_output=True, text=True, encoding='utf-8', timeout=180)
    if result.returncode:
        raise RuntimeError(f'Docker {args[:3]} failed: {result.stderr}')
    return result.stdout


def http(path, method='GET', body=None, token=None, expected=200, base=GATEWAY):
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    req = urllib.request.Request(base + path, headers=headers, method=method,
                                 data=None if body is None else json.dumps(body).encode())
    try:
        response = urllib.request.urlopen(req, timeout=8)
    except urllib.error.HTTPError as exc:
        response = exc
    with response:
        raw, status = response.read(), response.status
    assert status in ((expected,) if isinstance(expected, int) else expected), (method, path, status)
    return json.loads(raw) if raw.startswith((b'{', b'[')) else raw.decode()


def wait_for(check, timeout=75):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if check():
                return
        except (OSError, AssertionError, urllib.error.URLError):
            pass
        time.sleep(1)
    raise AssertionError('Timed out waiting for ' + check.__name__)


def services():
    return http('/v1/agent/services', base=CONSUL)


def consul_healthy():
    registered = services()
    checks = http('/v1/agent/checks', base=CONSUL)
    return all(s in registered and checks.get('service:' + s, {}).get('Status') == 'passing'
               for s in ('auth', 'catalog-1', 'catalog-2', 'order', 'graphql'))


def sample(label, expected):
    ids = [http('/api/catalog/products')['instance_id'] for _ in range(12)]
    assert set(ids) == set(expected), ids
    record(label, instance_ids=ids, requests=len(ids), all_http_200=True)


def crud(instance):
    book = {'name': 'Integration test book', 'price': 123.45, 'stock': 3}
    created = http('/api/catalog/products', 'POST', book, expected=201)
    assert created['instance_id'] == instance
    assert all(created[k] == v for k, v in book.items())
    path = '/api/catalog/products/' + str(created['id'])
    listing = http('/api/catalog/products')
    assert listing['instance_id'] == instance and created in listing['products']
    assert http(path) == created
    updated = http(path, 'PUT', {'price': 99.5, 'stock': 7})
    assert updated['price'] == 99.5 and updated['stock'] == 7 and updated['name'] == book['name']
    assert http(path) == updated
    http(path, 'DELETE')
    http(path, expected=404)
    assert all(p['id'] != created['id'] for p in http('/api/catalog/products')['products'])
    record('catalog_crud', instance_id=instance, post=201, list=200, get=200, put=200, delete=200, get_after_delete=404)


def all_healthy():
    rows = [json.loads(line) for line in docker('compose', 'ps', '--format', 'json').splitlines() if line.strip()]
    return len(rows) == 7 and all(r['State'] == 'running' and r['Health'] == 'healthy' for r in rows)


def orders_graphql():
    # catalog-2 is stopped: product creation and GraphQL read use the same store.
    email = 'order_' + str(time.time_ns()) + '@example.com'
    one = http('/api/catalog/products', 'POST', {'name': 'GraphQL book', 'price': 250, 'stock': 8}, expected=201)
    two = http('/api/catalog/products', 'POST', {'name': 'Second book', 'price': 350}, expected=201)
    page = http('/api/catalog/products?skip=1&limit=1')
    assert page['total'] == 2 and page['skip'] == 1 and page['limit'] == 1 and page['products'][0]['id'] == two['id']
    http('/api/catalog/products?skip=-1', expected=422)
    http('/api/catalog/products?limit=101', expected=422)
    http('/api/catalog/products', 'POST', {'name': 'Invalid', 'price': -1}, expected=422)
    http('/api/catalog/products/' + str(one['id']), 'PUT', {'stock': -1}, expected=422)
    order = http('/api/orders', 'POST', {'user_id': email, 'items': [{'product_id': one['id'], 'quantity': 2}, {'product_id': two['id'], 'quantity': 1}]}, expected=201)
    assert order['status'] == 'pending' and order['user_id'] == email
    assert http('/api/orders/' + order['id']) == order
    from urllib.parse import urlencode
    assert http('/api/orders?' + urlencode({'user_id': email})) == [order]
    http('/api/orders/not-found', expected=404)
    http('/api/orders', expected=422)
    http('/api/orders', 'POST', {'user_id': email, 'items': [{'product_id': one['id'], 'quantity': 0}]}, expected=422)
    query = """query($user: String!) { ordersByUserId(userId: $user) { id userId status items { productId quantity product { id name price stock } } } }"""
    response = http('/graphql', 'POST', {'query': query, 'variables': {'user': email}})
    assert not response.get('errors'), response
    result = response['data']['ordersByUserId']
    assert len(result) == 1 and result[0]['id'] == order['id'] and result[0]['userId'] == email
    items = result[0]['items']
    assert items[0]['quantity'] == 2 and items[0]['product']['id'] == one['id'] and items[0]['product']['name'] == 'GraphQL book'
    assert items[1]['product']['id'] == two['id'] and items[1]['product']['price'] == 350
    missing = http('/graphql', 'POST', {'query': query, 'variables': {'user': 'nobody-' + email}})
    assert missing.get('errors') and missing.get('data') is None
    http('/api/catalog/products/' + str(one['id']), 'DELETE')
    missing = http('/graphql', 'POST', {'query': query, 'variables': {'user': email}})
    assert missing.get('errors') and missing.get('data') is None
    http('/api/catalog/products/' + str(two['id']), 'DELETE')
    record('lab3_orders_graphql', order_post=201, order_get=200, user_orders=200,
           graphql_http=200, products_joined=2, pagination=True, invalid_inputs=422,
           missing_user_and_product='GraphQL errors', scenario='one active catalog')


def main():
    OUT.mkdir(exist_ok=True)
    success = False
    try:
        rows = [json.loads(line) for line in docker('compose', 'ps', '--format', 'json').splitlines() if line.strip()]
        assert {r['Service'] for r in rows} == {'auth', 'catalog-1', 'catalog-2', 'order', 'graphql', 'nginx', 'consul'}
        assert all(r['State'] == 'running' and r['Health'] == 'healthy' for r in rows), rows
        for name in ('auth', 'catalog-1', 'catalog-2', 'order', 'graphql'):
            cid = docker('compose', 'ps', '-q', name).strip()
            bindings = json.loads(docker('inspect', '--format', '{{json .HostConfig.PortBindings}}', cid))
            assert not bindings, (name, bindings)
        images = [docker('inspect', '--format', '{{.Image}}', name).strip() for name in ('catalog-1', 'catalog-2')]
        assert images[0] == images[1]
        (OUT / 'docker-compose-ps.txt').write_text(docker('compose', 'ps'), encoding='utf-8')
        record('docker', seven_running_healthy=True, api_ports_not_published=True, catalog_image=images[0])
        wait_for(consul_healthy)
        (OUT / 'consul-services.json').write_text(json.dumps(services(), indent=2), encoding='utf-8')
        (OUT / 'consul-checks.json').write_text(json.dumps(http('/v1/agent/checks', base=CONSUL), indent=2), encoding='utf-8')
        assert 'html' in http('/ui/', base=CONSUL).lower()
        record('consul', services=['auth', 'catalog-1', 'catalog-2', 'order', 'graphql'], checks='passing', ui_http=200)
        for prefix in ('auth', 'catalog', 'orders'):
            docs = http('/api/' + prefix + '/api-docs')
            assert 'swagger-ui' in docs and '/api/' + prefix + '/openapi.json' in docs
            schema = http('/api/' + prefix + '/openapi.json')
            assert schema['paths']
        assert 'swagger-ui' in http('/auth/docs')
        assert 'instance_id' in http('/catalog/products')
        record('swagger_and_legacy_routes', passed=True)
        user = {'email': 'integration_' + str(time.time_ns()) + '@example.com', 'password': 'test-password-for-lab'}
        http('/api/auth/register', 'POST', user)
        http('/api/auth/register', 'POST', user, expected=400)
        http('/api/auth/login', 'POST', {**user, 'password': 'wrong'}, expected=401)
        token = http('/api/auth/login', 'POST', user)['access_token']
        head, payload, signature = token.split('.')
        secret = os.environ.get('SECRET_KEY')
        if not secret:
            secret = next(line.split('=', 1)[1].strip() for line in (ROOT / '.env').read_text().splitlines() if line.startswith('SECRET_KEY='))
        decode = lambda value: base64.urlsafe_b64decode(value + '=' * (-len(value) % 4))
        assert json.loads(decode(head))['alg'] == 'HS256'
        assert hmac.compare_digest(hmac.new(secret.encode(), (head + '.' + payload).encode(), hashlib.sha256).digest(), decode(signature))
        claims = json.loads(decode(payload))
        assert claims['sub'] == user['email'] and claims['exp'] > time.time()
        me = http('/api/auth/me', token=token)
        assert me['email'] == user['email']
        http('/api/auth/me', expected=401)
        http('/api/auth/me', token='not-a-jwt', expected=401)
        # Verify Passlib is used in the running image, including salted hashes.
        docker('compose', 'exec', '-T', 'auth', 'python', '-c',
               "from main import hash_password, verify_password; a=hash_password('test'); b=hash_password('test'); assert a.startswith('$pbkdf2-sha256$') and a != b; assert verify_password('test',a) and not verify_password('wrong',a)")
        record('auth', register=200, login=200, jwt_signature_verified=True, me=me,
               no_token=401, invalid_token=401, duplicate_register=400, wrong_password=401, passlib_salted_hash=True)
        sample('balance_before', ['catalog-1', 'catalog-2'])
        docker('stop', 'catalog-2')
        wait_for(lambda: 'catalog-2' not in services())
        record('deregister', service='catalog-2', absent_from_consul=True)
        crud('catalog-1')
        orders_graphql()
        docker('start', 'catalog-2')
        wait_for(consul_healthy)
        time.sleep(6)
        sample('balance_before_failure', ['catalog-1', 'catalog-2'])
        docker('stop', 'catalog-1')
        sample('failover_immediate', ['catalog-2'])
        wait_for(lambda: 'catalog-1' not in services())
        record('deregister', service='catalog-1', absent_from_consul=True)
        crud('catalog-2')
        docker('start', 'catalog-1')
        wait_for(consul_healthy)
        time.sleep(6)
        sample('balance_restored', ['catalog-1', 'catalog-2'])
        # Consul starts later: apps remain available and retry registration.
        docker('compose', 'stop', 'consul')
        docker('restart', 'catalog-1')
        time.sleep(6)
        # A fresh dev agent loses the old registry, so this proves registration
        # recovery rather than merely checking entries retained by the old agent.
        docker('compose', 'up', '-d', '--no-deps', '--force-recreate', '--renew-anon-volumes', 'consul')
        wait_for(consul_healthy)
        record('consul_late_start', all_services_reregistered=True)
        time.sleep(6)
        sample('balance_final', ['catalog-1', 'catalog-2'])
        for service in ('auth', 'order', 'graphql'):
            docker('compose', 'stop', service)
            wait_for(lambda: service not in services())
            record('deregister', service=service, absent_from_consul=True)
            docker('compose', 'start', service)
        wait_for(consul_healthy)
        success = True
    finally:
        try:
            docker('compose', 'start', 'consul', 'auth', 'catalog-1', 'catalog-2', 'order', 'graphql', 'nginx')
            wait_for(consul_healthy)
            wait_for(all_healthy)
            (OUT / 'docker-compose-ps-final.txt').write_text(docker('compose', 'ps'), encoding='utf-8')
        except Exception:
            success = False
            raise
        finally:
            record('result', passed=success)
            (OUT / 'integration-results.json').write_text(json.dumps(EVENTS, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
