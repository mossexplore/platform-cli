import io
from unittest.mock import patch

from wiserec_cli.cli import configure_windows_output


def test_redirected_windows_streams_preserve_chinese():
    buffers = [io.BytesIO(), io.BytesIO()]
    streams = [io.TextIOWrapper(buffer, encoding='cp1252') for buffer in buffers]
    with patch('sys.platform', 'win32'), patch('sys.stdout', streams[0]), patch('sys.stderr', streams[1]):
        configure_windows_output()
        for stream in streams:
            stream.write('权限管理')
            stream.flush()
    for buffer in buffers:
        assert buffer.getvalue().decode('utf-8') == '权限管理'


def test_other_platforms_keep_their_encoding():
    stream = io.TextIOWrapper(io.BytesIO(), encoding='latin1')
    with patch('sys.platform', 'linux'), patch('sys.stdout', stream):
        configure_windows_output()
    assert stream.encoding == 'latin1'


def test_interactive_windows_stream_is_unchanged():
    stream = io.TextIOWrapper(io.BytesIO(), encoding='cp1252')
    with patch('sys.platform', 'win32'), patch('sys.stdout', stream), patch.object(stream, 'isatty', return_value=True):
        configure_windows_output()
    assert stream.encoding == 'cp1252'
