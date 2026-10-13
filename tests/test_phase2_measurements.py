import unittest
from scripts.measure_phase2_routes import measured_oracle, failure_class, usable_timing


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

    def test_system_error_retained_with_cost_never_correct(self):
        rows=self.records()
        rows[1].update(is_error=True,latency_eligible=False,retrieval_errors=['CypherSyntaxError: invalid ENDS_WITH'])
        self.assertEqual(failure_class(rows[1]),'system')
        self.assertTrue(usable_timing(rows[1]))
        self.assertEqual(measured_oracle(rows)[0]['oracle_route'],'hybrid')

    def test_transport_retry_contaminates_success(self):
        row=self.records()[0]
        row.update(retry_events=[dict(status='error',provider_status_code=503)])
        self.assertEqual(failure_class(row),'infrastructure')
        self.assertFalse(usable_timing(row))

    def test_unknown_failure_not_silently_retried(self):
        row=self.records()[0]
        row.update(is_error=True,error_type='NovelFailure')
        self.assertEqual(failure_class(row),'unclassified')
        self.assertFalse(usable_timing(row))
