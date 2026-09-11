import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, call, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import pip_tool as tool


class RecoveryTests(unittest.TestCase):
    def test_continue_requires_confirmed_overview(self):
        pip = Mock()
        with patch('builtins.input', side_effect=['Y', '']):
            self.assertTrue(tool.recover_batch(pip, ['next']))
        pip.check_origin.assert_called_once()
        pip.ready_overview.assert_called_once()

    def test_decline_stops_batch(self):
        with patch('builtins.input', side_effect=['n', '']):
            self.assertFalse(tool.recover_batch(Mock(), ['next']))

    def test_broken_overview_stops_batch(self):
        pip = Mock()
        pip.ready_overview.side_effect = RuntimeError()
        with patch('builtins.input', side_effect=['y', '']):
            self.assertFalse(tool.recover_batch(pip, ['next']))
        pip.hide.assert_not_called()

    def test_successes_preserved_across_skipped_order(self):
        pip = Mock()
        pip.process_with_session.side_effect = ['HOTOVO', RuntimeError('failure'), 'HOTOVO']
        journal = Mock()
        answers = ['WHS_SO_00000000001', 'WHS_SO_00000000002', 'WHS_SO_00000000003', '', 'y', 'y', '', '', '..', '0']
        with patch.object(sys, 'argv', ['pip_tool.py', '--instance', 'test', '--execute']), \
             patch.object(tool, 'read_config', return_value={'instances': {'test': {'url': 'https://example.com/'}}}), \
             patch.object(tool, 'open_browser'), patch.object(tool, 'Pip', return_value=pip), \
             patch.object(tool, 'Journal', return_value=journal), patch.object(tool, 'close_browser'), \
             patch.object(tool, 'print_teams') as report, patch('builtins.input', side_effect=answers):
            tool.main()
        self.assertEqual(pip.process_with_session.call_args_list,
                         [call('WHS_SO_00000000001', True), call('WHS_SO_00000000002', True), call('WHS_SO_00000000003', True)])
        report.assert_called_once_with([('WHS_SO_00000000001', 'HOTOVO'), ('WHS_SO_00000000003', 'HOTOVO')], True)
