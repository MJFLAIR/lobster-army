import os
import shutil
from workflows.tools.write_file import write_file

# Establish temp sandbox space natively tracking tests organically
def setup_module(module):
    if not os.path.exists("sandbox"):
        os.makedirs("sandbox")
    if not os.path.exists("sandbox/test"):
        os.makedirs("sandbox/test")
        
def teardown_module(module):
    if os.path.exists("sandbox/test"):
        shutil.rmtree("sandbox/test")

def test_write_success():
    result = write_file("test/a.py", "print(1)", overwrite=True)
    assert result["status"] == "success"
    assert os.path.exists(result["path"])

def test_no_overwrite():
    write_file("test/b.py", "1", overwrite=True)
    result = write_file("test/b.py", "2", overwrite=False)
    assert result["status"] == "failed"
    assert "exists" in result["error"].lower()

def test_path_traversal():
    result = write_file("../hack.py", "bad")
    assert result["status"] == "failed"

def test_outside_sandbox():
    result = write_file("/etc/passwd", "bad")
    assert result["status"] == "failed"
