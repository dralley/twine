# Copyright 2014 Ian Cordasco
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from __future__ import unicode_literals

import os
import textwrap

import pretend
import pytest

from twine.commands import upload
from twine import package, cli, exceptions, settings
import twine

import helpers

WHEEL_FIXTURE = 'tests/fixtures/twine-1.5.0-py2.py3-none-any.whl'


def test_ensure_wheel_files_uploaded_first():
    files = upload.group_wheel_files_first(["twine/foo.py",
                                            "twine/first.whl",
                                            "twine/bar.py",
                                            "twine/second.whl"])
    expected = ["twine/first.whl",
                "twine/second.whl",
                "twine/foo.py",
                "twine/bar.py"]
    assert expected == files


def test_ensure_if_no_wheel_files():
    files = upload.group_wheel_files_first(["twine/foo.py",
                                            "twine/bar.py"])
    expected = ["twine/foo.py",
                "twine/bar.py"]
    assert expected == files


def test_find_dists_expands_globs():
    files = sorted(upload.find_dists(['twine/__*.py']))
    expected = [os.path.join('twine', '__init__.py'),
                os.path.join('twine', '__main__.py')]
    assert expected == files


def test_find_dists_errors_on_invalid_globs():
    with pytest.raises(ValueError):
        upload.find_dists(['twine/*.rb'])


def test_find_dists_handles_real_files():
    expected = ['twine/__init__.py', 'twine/__main__.py', 'twine/cli.py',
                'twine/utils.py', 'twine/wheel.py']
    files = upload.find_dists(expected)
    assert expected == files


def test_get_config_old_format(tmpdir):
    pypirc = os.path.join(str(tmpdir), ".pypirc")

    with open(pypirc, "w") as fp:
        fp.write(textwrap.dedent("""
            [server-login]
            username:foo
            password:bar
        """))

    try:
        settings.Settings(
            repository="pypi", sign=None, identity=None, username=None,
            password=None, comment=None, cert=None, client_cert=None,
            sign_with=None, config_file=pypirc, skip_existing=False,
            repository_url=None, verbose=None,
        )
    except KeyError as err:
        assert err.args[0] == (
            "Missing 'pypi' section from the configuration file\n"
            "or not a complete URL in --repository-url.\n"
            "Maybe you have a out-dated '{0}' format?\n"
            "more info: "
            "https://docs.python.org/distutils/packageindex.html#pypirc\n"
        ).format(pypirc)


def test_deprecated_repo(tmpdir):
    with pytest.raises(exceptions.UploadToDeprecatedPyPIDetected) as err:
        pypirc = os.path.join(str(tmpdir), ".pypirc")
        dists = ["tests/fixtures/twine-1.5.0-py2.py3-none-any.whl"]

        with open(pypirc, "w") as fp:
            fp.write(textwrap.dedent("""
                [pypi]
                repository: https://pypi.python.org/pypi/
                username:foo
                password:bar
            """))

        upload_settings = settings.Settings(
            repository="pypi", sign=None, identity=None, username=None,
            password=None, comment=None, cert=None, client_cert=None,
            sign_with=None, config_file=pypirc, skip_existing=False,
            repository_url=None, verbose=None,
        )

        upload.upload(upload_settings, dists)

        assert err.args[0] == (
            "You're trying to upload to the legacy PyPI site "
            "'https://pypi.python.org/pypi/'. "
            "Uploading to those sites is deprecated. \n "
            "The new sites are pypi.org and test.pypi.org. Try using "
            "https://upload.pypi.org/legacy/ "
            "(or https://test.pypi.org/legacy/) "
            "to upload your packages instead. "
            "These are the default URLs for Twine now. \n "
            "More at "
            "https://packaging.python.org/guides/migrating-to-pypi-org/ ."
            )


def test_skip_existing_skips_files_already_on_PyPI(monkeypatch):
    response = pretend.stub(
        status_code=400,
        reason='A file named "twine-1.5.0-py2.py3-none-any.whl" already '
               'exists for twine-1.5.0.')

    pkg = package.PackageFile.from_filename(WHEEL_FIXTURE, None)
    assert upload.skip_upload(response=response,
                              skip_existing=True,
                              package=pkg) is True


def test_skip_existing_skips_files_already_on_pypiserver(monkeypatch):
    # pypiserver (https://pypi.org/project/pypiserver) responds with a
    # 409 when the file already exists.
    response = pretend.stub(
        status_code=409,
        reason='A file named "twine-1.5.0-py2.py3-none-any.whl" already '
               'exists for twine-1.5.0.')

    pkg = package.PackageFile.from_filename(WHEEL_FIXTURE, None)
    assert upload.skip_upload(response=response,
                              skip_existing=True,
                              package=pkg) is True


def test_skip_upload_respects_skip_existing(monkeypatch):
    response = pretend.stub(
        status_code=400,
        reason='A file named "twine-1.5.0-py2.py3-none-any.whl" already '
               'exists for twine-1.5.0.')

    pkg = package.PackageFile.from_filename(WHEEL_FIXTURE, None)
    assert upload.skip_upload(response=response,
                              skip_existing=False,
                              package=pkg) is False


def test_values_from_env(monkeypatch):
    def none_upload(*args, **kwargs):
        pass

    replaced_upload = pretend.call_recorder(none_upload)
    monkeypatch.setattr(twine.commands.upload, "upload", replaced_upload)
    testenv = {"TWINE_USERNAME": "pypiuser",
               "TWINE_PASSWORD": "pypipassword",
               "TWINE_CERT": "/foo/bar.crt"}
    with helpers.set_env(**testenv):
        cli.dispatch(["upload", "path/to/file"])
    upload_settings = replaced_upload.calls[0].args[0]
    assert "pypipassword" == upload_settings.password
    assert "pypiuser" == upload_settings.username
    assert "/foo/bar.crt" == upload_settings.cacert
