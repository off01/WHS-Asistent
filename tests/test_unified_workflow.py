import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import pip_tool as tool
import hw_workflow as hw

A = 'WHS_SO_08000006785'
B = 'WHS_SO_08000006786'


class UnifiedTests(unittest.TestCase):
    def test_short_and_long_realization_aliases_match(self):
        self.assertEqual(tool.extract_orders(A + ' --r\n' + A + ' --realizace'), {A: 'realizace'})
        for flag in ('--rr', '--r-extra', '--r=1'):
            with self.subTest(flag=flag), self.assertRaises(ValueError):
                tool.extract_orders(A + ' ' + flag)

    def test_startup_help_does_not_read_config_or_open_browser(self):
        for flag in ('--help', '--h'):
            with patch.object(sys, 'argv', ['pip_tool.py', flag]), \
                 patch.object(tool, 'read_config') as config, \
                 patch.object(tool, 'open_browser') as browser, \
                 patch('sys.stdout'):
                with self.assertRaises(SystemExit) as result:
                    tool.main()
                self.assertEqual(result.exception.code, 0)
                config.assert_not_called()
                browser.assert_not_called()

    def test_mixed_batch(self):
        self.assertEqual(tool.extract_orders(A + ' --realizace\n' + B), {A: 'realizace', B: 'all'})

    def test_bad_flags_and_conflicting_duplicates_rejected(self):
        for text in (A + ' --realizac', '--realizace ' + A, A + '\n--realizace',
                     A + ' --realizace\n' + A):
            with self.subTest(text=text), self.assertRaises(ValueError):
                tool.extract_orders(text)

    def test_bad_length_still_rejected(self):
        with self.assertRaises(ValueError):
            tool.extract_orders(A + '0 --realizace')

    def test_socket_only_never_runs_hardware(self):
        pip = Mock()
        with patch.object(tool.Pip, 'process', return_value='HOTOVO'), patch.object(hw, 'HardwarePip') as hardware:
            self.assertEqual(hw.run_workflow(pip, A, True, 'realizace'), 'REALIZACE_HOTOVO')
        hardware.assert_not_called()
        pip.journal.write.assert_called_once_with(A, 'HOTOVO')

    def test_full_flow_stops_after_socket_until_cm_ready(self):
        pip = Mock()
        pip.status.side_effect = ['WHS HFC Instalace - Čeká na přiřazení',
                                  'WHS HFC Instalace - Čeká se na odpověď WHS partnera']
        with patch.object(tool.Pip, 'process', return_value='HOTOVO'), patch.object(hw, 'HardwarePip') as hardware:
            self.assertEqual(hw.run_workflow(pip, A, True, 'all'), 'CEKA_NA_CM')
        hardware.assert_not_called()
        self.assertEqual(tool.teams_text([(A, 'CEKA_NA_CM')], True), '')

    def test_cm_ready_goes_to_hardware_without_socket_submission(self):
        pip = Mock()
        pip.status.return_value = 'WHS HFC Instalace - Registrace CM provedena'
        with patch.object(tool.Pip, 'process') as socket, patch.object(hw, 'HardwarePip') as hardware:
            hardware.return_value.process.return_value = 'HOTOVO'
            self.assertEqual(hw.run_workflow(pip, A, True, 'all'), 'HOTOVO')
        socket.assert_not_called()
        hardware.return_value.process.assert_called_once_with(A, True)

    def test_report_distinguishes_scope(self):
        self.assertEqual(tool.teams_text([(A, 'REALIZACE_HOTOVO'), (B, 'HOTOVO')], True),
                         B + ' dokončeno\n' + A + ' realizace dokončena')
