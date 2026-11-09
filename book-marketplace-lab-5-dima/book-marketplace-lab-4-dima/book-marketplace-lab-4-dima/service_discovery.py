"""Shared Consul lifecycle for all services; no third-party HTTP dependency."""
import asyncio
from contextlib import asynccontextmanager
import json
import logging
import os
from urllib.error import URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

logger = logging.getLogger('uvicorn.error')


def consul_lifespan(default_name: str, default_port: int):
    @asynccontextmanager
    async def lifespan(app):
        base = os.getenv('CONSUL_HTTP_ADDR', '').rstrip('/')
        if not base:  # Local development without Consul is supported.
            yield
            return
        service_id = os.getenv('INSTANCE_NAME', default_name)
        address = os.getenv('SERVICE_HOST', service_id)
        port = int(os.getenv('PORT', str(default_port)))
        definition = {
            'ID': service_id,
            'Name': service_id,
            'Address': address,
            'Port': port,
            'Tags': [default_name, 'book-marketplace'],
            'Check': {
                'HTTP': f'http://{address}:{port}/health',
                'Interval': '5s',
                'Timeout': '2s',
                'DeregisterCriticalServiceAfter': '1m',
            },
        }

        def call(path, method='GET', body=None):
            request = Request(base + '/v1/agent/' + path, method=method,
                              data=None if body is None else json.dumps(body).encode(),
                              headers={'Content-Type': 'application/json'})
            with urlopen(request, timeout=2) as response:
                raw = response.read()
            return json.loads(raw) if raw else None

        stopping = asyncio.Event()

        async def register_loop():
            delay = 1
            while not stopping.is_set():
                try:
                    known = await asyncio.to_thread(call, 'services')
                    if service_id not in known:
                        await asyncio.to_thread(call, 'service/register', 'PUT', definition)
                        logger.info('Registered %s in Consul', service_id)
                    delay = 10
                except (URLError, OSError, ValueError) as exc:
                    logger.warning('Consul unavailable for %s; retry in %ss: %s', service_id, delay, exc)
                try:
                    await asyncio.wait_for(stopping.wait(), timeout=delay)
                except asyncio.TimeoutError:
                    pass
                delay = min(delay * 2, 10)

        task = asyncio.create_task(register_loop())
        try:
            yield
        finally:
            # Let any in-flight registration finish before deregistration.
            stopping.set()
            await task
            for attempt in range(3):
                try:
                    await asyncio.to_thread(call, 'service/deregister/' + quote(service_id, safe=''), 'PUT')
                    logger.info('Deregistered %s from Consul', service_id)
                    break
                except (URLError, OSError, ValueError) as exc:
                    logger.warning('Consul deregistration failed for %s: %s', service_id, exc)
                    if attempt < 2:
                        await asyncio.sleep(0.5)

    return lifespan
