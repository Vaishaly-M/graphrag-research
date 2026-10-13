import unittest
from scripts.measure_phase2_routes import measured_oracle


class MeasuredOracleTests(unittest.TestCase):
    def records(self):
        return [dict(question_id='q',route=r,latency_s=t,recall_accuracy=1,
            latency_eligible=True,is_error=False,retry_events=[])
            for r,t in [('graph',3),('vector',1),('hybrid',2)]]

    def test_empirical_cost_not_ordinal(self):
        self.assertEqual(measured_oracle(self.records())[0]['oracle_route'],'vector')

    def test_cost_tie_uses_declared_route_order(self):
        rows=self.records()
        for row in rows:
            row['latency_s']=1
        self.assertEqual(measured_oracle(rows)[0]['oracle_route'],'graph')

    def test_rejects_errors_cache_and_retries(self):
        for change in [dict(is_error=True),dict(latency_eligible=False),dict(retry_events=[dict(status='error')])]:
            rows=self.records()
            rows[0].update(change)
            with self.assertRaises(ValueError):
                measured_oracle(rows)

    def test_no_correct_and_incomplete(self):
        rows=self.records()
        for row in rows:
            row['recall_accuracy']=0
        self.assertIsNone(measured_oracle(rows)[0]['oracle_route'])
        self.assertEqual(measured_oracle(rows[:2]),[])
