import json
import tempfile
import time
import unittest
import uuid
from pathlib import Path

from leds_fanatec_linux.commands import read_test_command, send_test_command


class CommandTests(unittest.TestCase):
    def test_test_command_is_written_atomically_and_validated(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "command.json"
            command_id = send_test_command("test_flag", "double_yellow", path=path)
            command = read_test_command(path)
            self.assertEqual(command, {
                "id": command_id,
                "action": "test_flag",
                "flag": "double_yellow",
            })

    def test_invalid_or_expired_commands_are_not_executed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "command.json"
            with self.assertRaises(ValueError):
                send_test_command("test_flag", "unknown", path=path)
            path.write_text(
                json.dumps(
                    {
                        "id": str(uuid.uuid4()),
                        "action": "test_rpm",
                        "flag": None,
                        "created_at": time.time() - 10,
                    }
                )
            )
            self.assertIsNone(read_test_command(path))


if __name__ == "__main__":
    unittest.main()
