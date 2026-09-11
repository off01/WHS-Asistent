import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import pip_tool as tool
import hw_workflow as hw

ORDER = 'WHS_SO_08000006878'


class CancelledTests(unittest.TestCase):
    def cancelled(self, cls=tool.Pip):
        pip = object.__new__(cls)
        pip.status = Mock(return_value='WHS HFC Instalace - Realizace zrušena')
        pip.open_order = Mock()
        pip.identity = Mock()
        pip.completed = Mock()
        pip.journal = Mock()
        pip.by_id = Mock(side_effect=AssertionError('No installation field on cancelled order'))
        pip.click_text = Mock()
        return pip

    def test_all_entry_points_stop_without_mutations(self):
        for prefix in tool.ORDER_PREFIXES:
            for execute in (False, True):
                for cls in (tool.Pip, hw.HardwarePip):
                    with self.subTest(prefix=prefix, execute=execute, cls=cls):
                        pip = self.cancelled(cls)
                        pip.status.return_value = prefix + tool.CANCELLED
                        self.assertEqual(pip.process(ORDER, execute), 'REALIZACE_ZRUSENA')
                        pip.completed.assert_not_called()
                        pip.by_id.assert_not_called()
                        pip.click_text.assert_not_called()
                        pip.journal.write.assert_not_called()

    def test_control_reports_cancelled_without_fields(self):
        pip = self.cancelled()
        with redirect_stdout(io.StringIO()) as output:
            self.assertEqual(pip.inspect_order(ORDER), 'REALIZACE_ZRUSENA')
        self.assertIn(tool.CANCELLED, output.getvalue())
        pip.by_id.assert_not_called()

    def test_full_workflow_does_not_enter_hardware(self):
        for mode in ('all', 'realizace'):
            pip = self.cancelled()
            with patch.object(hw, 'HardwarePip') as hardware:
                self.assertEqual(hw.run_workflow(pip, ORDER, True, mode), 'REALIZACE_ZRUSENA')
            hardware.assert_not_called()
        self.assertEqual(tool.teams_text([(ORDER, 'REALIZACE_ZRUSENA')], True), '')

    def test_open_cancelled_detail_does_not_require_installation_controls(self):
        pip = self.cancelled()
        pip.find_order = Mock()
        pip.interact = Mock()
        tool.Pip.open_order(pip, ORDER)
        pip.identity.assert_called_once_with(ORDER)
        pip.click_text.assert_not_called()
        pip.by_id.assert_not_called()

    def test_terminal_cancelled_resolves_pending_socket_submission(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(tool, 'DATA', Path(folder)):
            journal = tool.Journal('int', 'https://example.com/')
            journal.write(ORDER, 'ODESILANI')
            self.assertTrue(journal.uncertain(ORDER))
            journal.write(ORDER, 'REALIZACE_ZRUSENA')
            self.assertFalse(journal.uncertain(ORDER))
