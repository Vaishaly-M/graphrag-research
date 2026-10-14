"""Retry provider status codes without relying on English error messages."""
import unittest
import tempfile
from pathlib import Path
from itertools import cycle
from types import SimpleNamespace
from unittest.mock import Mock, patch
from src.llm import GeminiClient, retryable
from src.evaluation.telemetry import Measurement, measured


class ProviderError(Exception):
    def __init__(self, code, message=''):
        super().__init__(message)
        self.code = code


class RetryStatusTests(unittest.TestCase):
    def test_transient_statuses_without_message(self):
        for code in (408, 429, 500, 502, 503, 504, '504'):
            with self.subTest(code=code):
                self.assertTrue(retryable(ProviderError(code)))

    def test_deadline_exceeded_is_retryable(self):
        self.assertTrue(retryable(ProviderError(504, 'DEADLINE_EXCEEDED')))

    def test_permanent_status_overrides_misleading_message(self):
        for code in (400, 401, 403, 404):
            with self.subTest(code=code):
                self.assertFalse(retryable(ProviderError(code, 'connection unavailable')))

    def test_response_status_fallback(self):
        error = Exception('')
        error.response = SimpleNamespace(status_code=503)
        self.assertTrue(retryable(error))

    def test_transport_message_fallback(self):
        self.assertTrue(retryable(ConnectionError('connection reset by peer')))
        self.assertFalse(retryable(ValueError('invalid answer')))

    def test_client_retries_504_and_stops_at_cap(self):
        for recover in (True, False):
            with self.subTest(recover=recover), tempfile.TemporaryDirectory() as directory:
                request = Mock(side_effect=[ProviderError(504), SimpleNamespace(text='OK')]
                               if recover else ProviderError(504))
                client = GeminiClient.__new__(GeminiClient)
                client.model, client.cache_enabled = 'fixture', False
                client.cache_dir, client.cache_namespace = Path(directory), 'test'
                client.interval, client._last_call = 0, {}
                client._key_cycle = cycle(['fixture'])
                client._clients = {'fixture': SimpleNamespace(models=SimpleNamespace(generate_content=request))}
                m = Measurement(event_path=Path(directory)/'events.jsonl')
                settings = {'retry.retries': 2, 'retry.base_delay_s': 0}
                with measured(m), patch('src.llm.config_get', side_effect=lambda k,d=None: settings.get(k,d)), patch('src.llm.time.sleep'), patch('src.llm.random.random', return_value=0):
                    if recover:
                        self.assertEqual(client.generate('test'), 'OK')
                    else:
                        with self.assertRaises(ProviderError):
                            client.generate('test')
                self.assertEqual(request.call_count, 2)
                self.assertEqual(m.events[0]['reason'], 'retry')
                self.assertEqual(m.events[0]['provider_status_code'], 504)
                self.assertEqual(m.events[-1]['reason'], 'completed' if recover else 'terminal')


if __name__ == '__main__':
    unittest.main()
