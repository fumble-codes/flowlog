import os
import sys
# Ensure current directory is in path
sys.path.append(os.getcwd())

os.environ["FLOWLOG_TUI_MODE"] = "1"
from main import app
from typer.testing import CliRunner

runner = CliRunner()
print("--- Running ai-add ---")
result = runner.invoke(app, ["ai-add", "verify tui stability 🌸"])
print(f"Exit Code: {result.exit_code}")
print("Output:")
print(result.output)
if result.exception:
    import traceback
    print("Exception:")
    traceback.print_exception(type(result.exception), result.exception, result.exception.__traceback__)

print("\n--- Running ai-summary ---")
result_s = runner.invoke(app, ["ai-summary"])
print(f"Exit Code: {result_s.exit_code}")
print("Output:")
print(result_s.output)
if result_s.exception:
    traceback.print_exception(type(result_s.exception), result_s.exception, result_s.exception.__traceback__)
