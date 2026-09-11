import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import pip_tool
import hw_workflow
import whs_asistent as setup
import launcher


class CheckTests(unittest.TestCase):
    def test_check_never_enters_submission_for_any_state_or_mode(self):
        for cls in (pip_tool.Pip, hw_workflow.HardwarePip):
            for state in ('Čeká na přiřazení', 'Čeká se na odpověď WHS partnera', 'Registrace CM provedena'):
                for mode in ('all', 'realizace'):
                    with self.subTest(cls=cls, state=state, mode=mode):
                        pip = object.__new__(cls)
                        pip.workflow = 'all'
                        pip.order_modes = {'WHS_SO_08000006785': mode}
                        pip.logged_out = Mock(return_value=False)
                        pip.open_order = Mock()
                        pip.identity = Mock()
                        pip.status = Mock(return_value='WHS HFC Instalace - ' + state)
                        pip.process = Mock(side_effect=AssertionError('submission path'))
                        pip.journal = Mock()
                        with patch.object(hw_workflow, 'run_workflow') as workflow, redirect_stdout(io.StringIO()) as output:
                            self.assertEqual(pip.process_with_session('WHS_SO_08000006785', False), 'KONTROLA_OK')
                        self.assertIn(state, output.getvalue())
                        pip.process.assert_not_called()
                        workflow.assert_not_called()
                        pip.journal.write.assert_not_called()

    def test_menu_two_does_not_enable_execution(self):
        with patch.object(launcher, 'read_config', return_value={'instances': {'int': {}}}), \
             patch('builtins.input', side_effect=['2', EOFError]), \
             patch.object(launcher, 'run_child') as child, redirect_stdout(io.StringIO()):
            with self.assertRaises(EOFError):
                launcher.main()
        self.assertNotIn('--execute', child.call_args.args[0])


class SetupTests(unittest.TestCase):
    def test_first_setup_asks_credentials_once_for_all_three(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(setup, 'DATA', Path(folder)), \
             patch('builtins.input', side_effect=['test-user', 'y']) as inputs, \
             patch.object(setup.getpass, 'getpass', side_effect=['test-secret', 'test-secret']) as passwords, \
             redirect_stdout(io.StringIO()):
            setup.wizard()
            config = setup.read_config()
        self.assertEqual(set(config['instances']), {'sys2', 'int', 'pre'})
        self.assertEqual(inputs.call_count, 2)
        self.assertEqual(passwords.call_count, 2)
        for name, entry in config['instances'].items():
            self.assertEqual(entry, dict(url=setup.DEFAULT_INSTANCES[name], login='test-user', password='test-secret'))

    def test_existing_credentials_reused_without_changing_existing_instance(self):
        original = {'instances': {'sys2': dict(url='https://custom.example/', login='user', password='secret')}}
        with tempfile.TemporaryDirectory() as folder, patch.object(setup, 'DATA', Path(folder)):
            setup.save_config(original)
            before = (Path(folder) / 'config.json').read_bytes()
            config = setup.read_config()
            self.assertEqual((Path(folder) / 'config.json').read_bytes(), before)
            self.assertEqual(config['instances']['sys2'], original['instances']['sys2'])
            with patch('builtins.input', return_value='y'), patch.object(setup.getpass, 'getpass') as passwords, redirect_stdout(io.StringIO()):
                setup.wizard()
            passwords.assert_not_called()
            self.assertEqual(set(setup.read_config()['instances']), {'sys2', 'int', 'pre'})

    def test_conflicting_credentials_do_not_choose_arbitrarily(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(setup, 'DATA', Path(folder)):
            original = {'instances': {'sys2': dict(login='a', password='one'), 'int': dict(login='b', password='two')}}
            setup.save_config(original)
            self.assertEqual(setup.read_config(), original)
