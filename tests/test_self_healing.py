import sys
import os
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from workflows.strategy.self_healing_loop import self_healing_execute

class TestSelfHealingLoop(unittest.TestCase):

    @patch('workflows.strategy.self_healing_loop.run_auto_fix_for_incident')
    def test_json_failure_retry(self, mock_run):
        # First call returns json_parse_error (mapped to invalid_llm_output)
        mock_run.side_effect = [
            {"status": "BLOCKED", "reason": "invalid_llm_output"},
            {"status": "PR_READY", "reason": "success"}
        ]
        
        incident = {"incident_hash": "test-1"}
        llm_mock = MagicMock()
        
        with self.assertLogs(level='INFO') as log:
            res = self_healing_execute(incident, None, llm_mock, "/path")
            
        self.assertEqual(mock_run.call_count, 2)
        self.assertEqual(res["status"], "PR_READY")
        
        retry_llm_run2 = mock_run.call_args_list[1][0][2]
        self.assertIn("JSON_FORMAT_ERROR", retry_llm_run2.correction_prompt)
        
        logs = "\n".join(log.output)
        self.assertIn("[SELF_HEAL_TRIGGER]", logs)
        self.assertIn("[SELF_HEAL_RETRY]", logs)
        self.assertIn("[SELF_HEAL_RESULT]", logs)

    @patch('workflows.strategy.self_healing_loop.run_auto_fix_for_incident')
    def test_git_apply_failure_retry(self, mock_run):
        mock_run.side_effect = [
            {"status": "BLOCKED", "reason": "patch_invalid"},
            {"status": "PATCH_READY", "reason": "success"} # Note: testing PATCH_READY handling
        ]
        
        res = self_healing_execute({"incident_hash": "test-2"}, None, MagicMock(), "/path")
        
        self.assertEqual(mock_run.call_count, 2)
        self.assertEqual(res["status"], "PATCH_READY")
        
        retry_llm_run2 = mock_run.call_args_list[1][0][2]
        self.assertIn("DIFF_FORMAT_ERROR", retry_llm_run2.correction_prompt)

    @patch('workflows.strategy.self_healing_loop.run_auto_fix_for_incident')
    def test_schema_failure_fail_fast(self, mock_run):
        mock_run.side_effect = [
            {"status": "BLOCKED", "reason": "schema_invalid"},
            {"status": "PR_READY", "reason": "success"}
        ]
        
        res = self_healing_execute({"incident_hash": "test-3"}, None, MagicMock(), "/path")
        self.assertEqual(mock_run.call_count, 1) # Fail fast on schema_invalid
        self.assertEqual(res["status"], "BLOCKED")

    @patch('workflows.strategy.self_healing_loop.run_auto_fix_for_incident')
    def test_non_retryable_failure(self, mock_run):
        # E.g. scope too wide
        mock_run.side_effect = [
            {"status": "BLOCKED", "reason": "scope_too_wide_files"}
        ]
        
        res = self_healing_execute({"incident_hash": "test-4"}, None, MagicMock(), "/path")
        
        self.assertEqual(mock_run.call_count, 1) # Only 1 run!
        self.assertEqual(res["status"], "BLOCKED")

    @patch('workflows.strategy.self_healing_loop.run_auto_fix_for_incident')
    def test_success_first_try(self, mock_run):
        mock_run.return_value = {"status": "PR_READY", "reason": "success"}
        res = self_healing_execute({"incident_hash": "test-5"}, None, MagicMock(), "/path")
        
        self.assertEqual(mock_run.call_count, 1) # Only 1 run!
        self.assertEqual(res["status"], "PR_READY")
        
    @patch('workflows.strategy.self_healing_loop.run_auto_fix_for_incident')
    def test_double_failure(self, mock_run):
        mock_run.side_effect = [
            {"status": "BLOCKED", "reason": "invalid_llm_output"},
            {"status": "FAILED", "reason": "model_error"}
        ]
        
        res = self_healing_execute({"incident_hash": "test-6"}, None, MagicMock(), "/path")
        
        self.assertEqual(mock_run.call_count, 2)
        self.assertEqual(res["status"], "BLOCKED") # Converted to blocked

    @patch('workflows.strategy.self_healing_loop.run_auto_fix_for_incident')
    def test_retry_recovers_successfully(self, mock_run):
        mock_run.side_effect = [
            {"status": "BLOCKED", "reason": "invalid_llm_output"},
            {"status": "PATCH_READY", "reason": "success"}
        ]
        
        incident = {"incident_hash": "test-behavior"}
        llm_mock = MagicMock()
        
        with self.assertLogs(level='INFO') as log:
            res = self_healing_execute(incident, None, llm_mock, "/path")
            
        self.assertEqual(mock_run.call_count, 2)
        self.assertEqual(res["status"], "PATCH_READY")
        
        logs = "\n".join(log.output)
        self.assertIn("[SELF_HEAL_TRIGGER]", logs)
        self.assertIn("[SELF_HEAL_RETRY]", logs)
        self.assertIn("[SELF_HEAL_RESULT]", logs)

if __name__ == '__main__':
    unittest.main()
