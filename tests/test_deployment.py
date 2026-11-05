"""Linux-only deployment regressions using synthetic credentials and mock Docker."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


linux = load('linux_deployment', 'linux/qqbridge_linux.py')
config = load('config_deployment', 'wsl/config_tool.py')


class DeploymentTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='qqbridge-deploy-tests-')
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.environment = patch.dict(os.environ, {k: v for k, v in os.environ.items() if not k.startswith('QQBRIDGE_')}, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def settings(self):
        return {'llm_base_url': 'https://example.invalid/v1', 'llm_model': 'fixture-model',
                'llm_api_key': 'synthetic-secret', 'owner_qq': '12345'}

    def rejected(self, fn, *args):
        output = io.StringIO()
        with contextlib.redirect_stderr(output), self.assertRaises(SystemExit):
            fn(*args)
        self.assertNotIn('synthetic-secret', output.getvalue())

    def test_config_environment_precedence_and_secret_boundary(self):
        path = self.base / 'config.json'
        path.write_text(json.dumps({'llm_model': 'json-model', 'http_proxy': ''}))
        args = linux.build_parser().parse_args(['install', '--config-file', str(path)])
        with patch.dict(os.environ, QQBRIDGE_LLM_MODEL='env-model', QQBRIDGE_LLM_API_KEY='synthetic-secret', QQBRIDGE_ALLOWED_GROUPS='[12345]'):
            settings = linux.load_install_settings(args)
        self.assertEqual(settings['llm_model'], 'env-model')
        self.assertEqual(settings['allowed_groups'], [12345])
        self.assertEqual(settings['llm_api_key'], 'synthetic-secret')
        path.write_text(json.dumps({'llm_api_key': 'synthetic-secret'}))
        self.rejected(linux.load_install_settings, args)
        path.write_text('[]')
        self.rejected(linux.load_install_settings, args)

    def test_headless_validation_never_prompts(self):
        with patch.object(linux, 'NON_INTERACTIVE', True), patch.object(linux, 'port_available', return_value=True), patch.object(linux, 'ask', side_effect=AssertionError('unexpected prompt')):
            result = linux.configured_core_answers(self.settings(), '127.0.0.1')
            self.assertEqual(result['allowed_users'], ['12345'])
            self.assertEqual(result['maibot_bind'], '127.0.0.1')
            for update in ({'llm_api_key': ''}, {'llm_model': ''}, {'llm_base_url': 'https://synthetic-secret@example.invalid'},
                           {'llm_client_type': 'invalid'}, {'owner_qq': 'abc'}, {'maibot_port': 6099},
                           {'maibot_port': 80}, {'allowed_groups': '12345'}):
                self.rejected(linux.configured_core_answers, {**self.settings(), **update}, '127.0.0.1')

    def test_sudo_preserves_only_configuration_names_without_secret_arguments(self):
        arguments = ['install', '--config-file=deploy.local.json', '--non-interactive']
        args = linux.build_parser().parse_args(arguments)
        with patch.object(linux.os, 'geteuid', return_value=1000), patch.object(linux.shutil, 'which', return_value='/usr/bin/sudo'), \
             patch.object(linux.os, 'execvp') as execute, patch.object(sys, 'argv', ['installer', *arguments]), \
             patch.dict(os.environ, QQBRIDGE_LLM_API_KEY='synthetic-secret', QQBRIDGE_UNRELATED_SECRET='unrelated'):
            linux.elevate_if_needed(args)
        command = execute.call_args.args[1]
        self.assertIn('-n', command)
        self.assertIn('--preserve-env=QQBRIDGE_LLM_API_KEY', command)
        self.assertNotIn('synthetic-secret', ' '.join(command))
        self.assertNotIn('QQBRIDGE_UNRELATED_SECRET', ' '.join(command))
        self.assertIn('--config-file=' + str(Path('deploy.local.json').resolve()), command)

    def test_headless_install_passes_answers_and_keeps_secrets_out_of_state(self):
        settings = self.settings()
        path = self.base / 'config.json'
        path.write_text(json.dumps({k: v for k, v in settings.items() if k != 'llm_api_key'}))
        args = linux.build_parser().parse_args(['install', '--config-file', str(path), '--non-interactive', '--install-root', str(self.base / 'install')])
        calls = []

        def fake_run(command, **kwargs):
            answers = json.loads(Path(command[command.index('--answers') + 1]).read_text())
            self.assertEqual(answers['llm_api_key'], 'synthetic-secret')
            calls.append(command)
            return subprocess.CompletedProcess(command, 0)

        with patch.object(linux, 'STATE_FILE', self.base / 'state.json'), patch.object(linux, 'verify_package'), \
             patch.object(linux, 'ensure_docker_installed'), patch.object(linux, 'ensure_docker_access'), \
             patch.object(linux, 'port_available', return_value=True), patch.object(linux, 'run', side_effect=fake_run), \
             patch.object(linux, 'ask', side_effect=AssertionError('unexpected prompt')), \
             patch.dict(os.environ, QQBRIDGE_LLM_API_KEY='synthetic-secret'), contextlib.redirect_stdout(io.StringIO()) as output:
            linux.command_install(args)
        self.assertEqual(len(calls), 1)
        self.assertNotIn('synthetic-secret', (self.base / 'state.json').read_text() + output.getvalue())
        self.assertFalse(Path(calls[0][calls[0].index('--answers') + 1]).exists())

    def test_proxy_install_update_clear_and_private_serialization(self):
        values = {}
        config.configure_proxies({'http_proxy': 'http://proxy.invalid:7890', 'all_proxy': 'socks5://proxy.invalid:1080', 'no_proxy': 'example.invalid'}, values)
        self.assertEqual(values['HTTPS_PROXY'], values['HTTP_PROXY'])
        self.assertTrue({'localhost', '127.0.0.1', 'napcat', 'maibot', 'example.invalid'} <= set(values['NO_PROXY'].split(',')))
        path = self.base / '.env'
        config.save_env(path, values)
        self.assertEqual(config.load_env(path)['ALL_PROXY'], 'socks5://proxy.invalid:1080')
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        config.configure_proxies({}, values)
        self.assertEqual(values['HTTPS_PROXY'], 'http://proxy.invalid:7890')
        config.configure_proxies({'http_proxy': '', 'all_proxy': ''}, values)
        self.assertEqual(values['HTTPS_PROXY'], '')
        self.assertEqual(values['ALL_PROXY'], '')
        for proxy in ('file:///tmp/secret', 'http://proxy.invalid', 'http://proxy.invalid:bad', 'http://proxy.invalid:7890\nSECRET'):
            self.rejected(config.configure_proxies, {'http_proxy': proxy}, {})

    def test_rendered_instance_receives_proxy_and_versioned_image(self):
        instance = self.base / 'instance'
        shutil.copytree(ROOT / 'payload/plugins', instance / 'plugins')
        path = self.base / 'answers.json'
        path.write_text(json.dumps({**self.settings(), 'http_proxy': 'http://proxy.invalid:7890'}))
        args = type('Args', (), dict(instance=str(instance), package=str(ROOT), answers=str(path), napcat_uid=1000, napcat_gid=1000))()
        config.command_install(args)
        env = config.load_env(instance / '.env')
        self.assertEqual(env['HTTPS_PROXY'], 'http://proxy.invalid:7890')
        self.assertEqual(env['MAIBOT_IMAGE'], 'ghcr.io/zuo-yan/qqbridge-maibot:v' + (ROOT / 'VERSION').read_text().strip())
        token = env['ONEBOT_TOKEN']
        path.write_text(json.dumps({'http_proxy': '', 'all_proxy': ''}))
        config.command_configure(args)
        env = config.load_env(instance / '.env')
        self.assertEqual(env['HTTPS_PROXY'], '')
        self.assertEqual(env['ONEBOT_TOKEN'], token)

    def test_compose_override_and_pull_fallback(self):
        root = self.base / 'installation with spaces'
        release = root / 'releases/fixture'
        release.mkdir(parents=True)
        (root / 'current').symlink_to('releases/fixture')
        instance = root / 'instances/default'
        instance.mkdir(parents=True)
        (instance / '.env').write_text('')
        override = instance / 'docker-compose.override.yml'
        override.write_text('services: {}\n')
        mock = self.base / 'bin'
        mock.mkdir()
        (mock / 'docker').write_text('#!/usr/bin/env python3\nimport json,os,sys\nwith open(os.environ["TRACE"],"a") as f: f.write(json.dumps(sys.argv[1:])+"\\n")\nif "pull" in sys.argv: sys.exit(int(os.environ.get("FAIL_PULL","0")))\nif "build" in sys.argv: sys.exit(int(os.environ.get("FAIL_BUILD","0")))\n')
        (mock / 'docker').chmod(0o755)
        trace = self.base / 'trace'
        env = dict(os.environ, PATH=str(mock) + ':' + os.environ['PATH'], TRACE=str(trace))
        command = ['bash', '-c', 'source "$1"; start_containers "$(id -un)" "$2" "$3"', 'fixture', str(ROOT / 'wsl/common.sh'), str(root), str(instance / '.env')]
        for pull, build, expected in [('0', '0', ['pull', 'up']), ('1', '0', ['pull', 'build', 'up']), ('1', '1', ['pull', 'build'])]:
            trace.write_text('')
            result = subprocess.run(command, env=dict(env, FAIL_PULL=pull, FAIL_BUILD=build), capture_output=True, text=True)
            self.assertEqual(result.returncode == 0, build == '0', result.stderr)
            calls = [json.loads(line) for line in trace.read_text().splitlines()]
            self.assertEqual([next(arg for arg in call if arg in {'pull', 'build', 'up'}) for call in calls], expected)
            self.assertTrue(all(str(override) in call for call in calls))
            self.assertTrue(all(call.index(str(release / 'compose.yaml')) < call.index(str(override)) for call in calls))
        (instance / 'compose.override.yml').write_text('services: {}\n')
        result = subprocess.run(command, env=env, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)

    def test_access_refuses_automation_and_ssh_uses_actual_ports(self):
        result = subprocess.run(['python3', str(ROOT / 'linux/qqbridge_linux.py'), 'access'], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('Token:', result.stdout + result.stderr)
        with contextlib.redirect_stdout(io.StringIO()) as output:
            linux.print_urls({'local_only': True, 'maibot_port': 28001, 'napcat_port': 16099, 'target_user': 'qqbot'})
        self.assertIn('-L 28001:127.0.0.1:28001', output.getvalue())
        self.assertIn('-L 16099:127.0.0.1:16099 qqbot@SERVER', output.getvalue())


if __name__ == '__main__':
    unittest.main(verbosity=2)
