import sys
import os
import json
import unittest
import tempfile
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from workflows.strategy.failure_pattern_tracker import record_failure_event, summarize_failure_stats
from workflows.strategy.self_healing_loop import self_healing_execute

class TestFailurePatternTracker(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.log_path = os.path.join(self.temp_dir.name, "test_failure_patterns.jsonl")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_build_failure_event(self):
        event = {
            "incident_id": "test-123",
            "initial_failure_type": "json_parse_error",
            "retry_triggered": True,
            "retry_count_used": 1,
            "retry_success": True,
            "final_status": "PATCH_READY"
        }
        record_failure_event(event, self.log_path)
        
        with open(self.log_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
            self.assertEqual(len(lines), 1)
            e = json.loads(lines[0])
            self.assertIn("timestamp", e)
            self.assertEqual(e["template_used"], "NONE")
            self.assertEqual(e["incident_id"], "test-123")

    def test_record_failure_event(self):
        event1 = {"incident_id": "A", "template_used": "T1"}
        event2 = {"incident_id": "B", "template_used": "T2"}
        
        record_failure_event(event1, self.log_path)
        record_failure_event(event2, self.log_path)
        
        with open(self.log_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
            self.assertEqual(len(lines), 2)
            self.assertEqual(json.loads(lines[0])["incident_id"], "A")
            self.assertEqual(json.loads(lines[1])["incident_id"], "B")

    def test_summarize_failure_stats(self):
        events = [
            {"incident_id": "A", "initial_failure_type": "err_1", "template_used": "T1", "retry_triggered": True, "retry_success": True, "final_status": "PATCH_READY"},
            {"incident_id": "B", "initial_failure_type": "err_2", "template_used": "T1", "retry_triggered": True, "retry_success": False, "final_status": "BLOCKED"},
            {"incident_id": "C", "initial_failure_type": "err_1", "template_used": "NONE", "retry_triggered": False, "retry_success": False, "final_status": "BLOCKED"}
        ]
        
        stats = summarize_failure_stats(events)
        self.assertEqual(stats["total_events"], 3)
        self.assertEqual(stats["total_retry_triggered"], 2)
        self.assertEqual(stats["total_retry_success"], 1)
        self.assertEqual(stats["retry_success_rate"], 0.5)
        self.assertEqual(stats["failures_by_type"]["err_1"], 2)
        self.assertEqual(stats["template_usage_count"]["T1"], 2)
        self.assertEqual(stats["final_status_count"]["BLOCKED"], 2)

    @patch('workflows.strategy.self_healing_loop.run_auto_fix_for_incident')
    @patch('workflows.strategy.failure_pattern_tracker.record_failure_event')
    def test_self_healing_integration_tracks_successful_retry(self, mock_record, mock_run):
        mock_run.side_effect = [
            {"status": "BLOCKED", "reason": "invalid_llm_output"},
            {"status": "PATCH_READY", "reason": "success"}
        ]
        
        incident = {"incident_hash": "test-integ-1"}
        llm_mock = MagicMock()
        
        with self.assertLogs(level='INFO'):
            self_healing_execute(incident, None, llm_mock, "/path")
            
        mock_record.assert_called_once()
        event_passed = mock_record.call_args[0][0]
        self.assertEqual(event_passed["incident_id"], "test-integ-1")
        self.assertEqual(event_passed["initial_failure_type"], "invalid_llm_output")
        self.assertEqual(event_passed["template_used"], "JSON_FORMAT_ERROR")
        self.assertTrue(event_passed["retry_triggered"])
        self.assertEqual(event_passed["retry_count_used"], 1)
        self.assertTrue(event_passed["retry_success"])
        self.assertEqual(event_passed["final_status"], "PATCH_READY")
        self.assertEqual(event_passed["final_failure_type"], "NONE")

    @patch('workflows.strategy.self_healing_loop.run_auto_fix_for_incident')
    @patch('workflows.strategy.failure_pattern_tracker.record_failure_event')
    def test_self_healing_integration_tracks_direct_block(self, mock_record, mock_run):
        mock_run.return_value = {"status": "BLOCKED", "reason": "scope_violation"}
        
        incident = {"incident_hash": "test-integ-2"}
        llm_mock = MagicMock()
        
        with self.assertLogs(level='INFO'):
            self_healing_execute(incident, None, llm_mock, "/path")
            
        mock_record.assert_called_once()
        event_passed = mock_record.call_args[0][0]
        self.assertEqual(event_passed["incident_id"], "test-integ-2")
        self.assertEqual(event_passed["initial_failure_type"], "scope_violation")
        self.assertEqual(event_passed["template_used"], "NONE")
        self.assertFalse(event_passed["retry_triggered"])
        self.assertEqual(event_passed["retry_count_used"], 0)
        self.assertFalse(event_passed["retry_success"])
        self.assertEqual(event_passed["final_status"], "BLOCKED")
        self.assertEqual(event_passed["final_failure_type"], "scope_violation")

if __name__ == '__main__':
    unittest.main()
