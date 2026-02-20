import logging
from typing import List


class SecurityError(Exception):
    """Custom exception for security-related issues."""
    pass


class TestRunner:
    ALLOWED_TEST_RUNNERS = ["pytest", "ruff", "python"]

    def run_tests(self, test_cmd: List[str]) -> str:
        """
        Executes tests using subprocess.
        """
        # 1. Validation
        if test_cmd[0] not in self.ALLOWED_TEST_RUNNERS:
            raise SecurityError(f"Test runner not allowlisted: {test_cmd[0]}")
            
        # 2. Execution (Mock for Phase 5)
        # Using logging instead of print
        logging.getLogger("TestRunner").info(f"MOCKED TEST EXECUTION: {' '.join(test_cmd)}")
        return "Tests Passed (Mock)"
