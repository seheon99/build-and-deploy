import os
from pathlib import Path
import subprocess
import tempfile
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
DIGEST = 'sha256:' + 'a' * 64
IMAGE = 'ghcr.io/example/app@' + DIGEST


class ActionsTest(unittest.TestCase):
    def setUp(self):
        self.deploy = yaml.safe_load((ROOT / 'deploy/action.yml').read_text())

    def resolve(self, **overrides):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'output'
            env = dict(os.environ, IMAGE=IMAGE, REGISTRY='', DIGEST='',
                       SERVICE_NAME='user-api', SSH_HOST='host', SSH_USER='user',
                       SSH_KEY='key', GITHUB_OUTPUT=str(output))
            env.update(overrides)
            result = subprocess.run(['bash', '-e', '-o', 'pipefail', '-c',
                                     self.deploy['runs']['steps'][0]['run']],
                                    env=env, capture_output=True, text=True)
            return result, output.read_text() if output.exists() else ''

    def test_reference_and_registry_digest(self):
        for inputs in ({}, {'IMAGE': '', 'REGISTRY': 'ghcr.io/example/app',
                            'DIGEST': DIGEST}):
            result, output = self.resolve(**inputs)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('image=' + IMAGE, output)
            self.assertIn('digest=' + DIGEST, output)
            self.assertIn('variable=USER_API', output)

    def test_invalid_inputs(self):
        for inputs in ({'IMAGE': 'ghcr.io/example/app:latest'},
                       {'IMAGE': IMAGE + '\nevil'},
                       {'IMAGE': '', 'REGISTRY': '', 'DIGEST': DIGEST},
                       {'SERVICE_NAME': 'app; touch /tmp/injected'},
                       {'SSH_KEY': ''},
                       {'IMAGE': IMAGE, 'DIGEST': 'sha256:' + 'b' * 64}):
            result, output = self.resolve(**inputs)
            self.assertNotEqual(result.returncode, 0, inputs)
            self.assertEqual(output, '')

    def test_remote_update_and_retry(self):
        step = self.deploy['runs']['steps'][1]
        script = step['with']['script']
        for expression, value in {
            '${{ steps.image.outputs.variable }}': 'USER_API',
            '${{ steps.image.outputs.image }}': IMAGE,
            '${{ steps.image.outputs.digest }}': DIGEST,
            '${{ inputs.service-name }}': 'user-api',
        }.items():
            script = script.replace(expression, value)
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            (directory / '.env').write_text('OTHER=keep\nUSER_API_IMAGE_DIGEST=old\n')
            docker = directory / 'docker'
            docker.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> docker.log\n')
            docker.chmod(0o755)
            for _ in range(2):
                subprocess.run(['bash', '-e', '-c', script], cwd=directory,
                               env=dict(os.environ, PATH=str(directory) + ':' + os.environ['PATH']),
                               check=True)
            self.assertEqual([line for line in (directory / '.env').read_text().splitlines() if line],
                             ['OTHER=keep', f'USER_API_IMAGE_DIGEST={DIGEST}', f'USER_API_IMAGE={IMAGE}'])
            self.assertEqual((directory / 'docker.log').read_text().splitlines(),
                             ['compose pull user-api', 'compose up -d --no-deps --no-build user-api'] * 2)

    def test_action_boundaries(self):
        build = yaml.safe_load((ROOT / 'build/action.yml').read_text())
        self.assertEqual(set(build['outputs']), {'image', 'digest'})
        self.assertFalse(any('ssh-action' in step.get('uses', '') for step in build['runs']['steps']))
        self.assertFalse(any('docker/' in step.get('uses', '') for step in self.deploy['runs']['steps']))
        for step in self.deploy['runs']['steps']:
            self.assertEqual(step['if'], "inputs.dry-run != 'true'")

    def test_build_outputs(self):
        build = yaml.safe_load((ROOT / 'build/action.yml').read_text())
        step = next(step for step in build['runs']['steps'] if step.get('id') == 'image')
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'output'
            subprocess.run(['bash', '-e', '-c', step['run']],
                           env=dict(os.environ, IMAGE='ghcr.io/example/app', DIGEST=DIGEST,
                                    GITHUB_OUTPUT=str(output)), check=True)
            self.assertEqual(output.read_text(), f'image={IMAGE}\ndigest={DIGEST}\n')
        self.assertEqual(step['if'], "inputs.dry-run != 'true'")
        push = next(step for step in build['runs']['steps'] if step.get('id') == 'build')
        self.assertEqual(push['with']['push'], "${{ inputs.dry-run != 'true' }}")


if __name__ == '__main__':
    unittest.main()
