from .harness import Harness
import pytest

fizzbuzz_workspace = Harness("repos/fizzbuzz_service")
fizzbuzz_workspace.initialize("")

def test_x_packages():
    result = fizzbuzz_workspace.x_packages()

    assert len(result) == 1
    package = result[0]

    assert "package" in package
    assert package["package"] == {'name': 'fizzbuzz_service'}

    assert "dependencies" in package

    dependencies = {d["attributes"]["name"] for d in package["dependencies"]}

    assert dependencies == {"cpython"}


def test_local_hover():
    uri = "file:///fizzbuzz_service/loopers/number_looper.py"
    line, col = 2, 7
    result = fizzbuzz_workspace.hover(uri, line, col)
    assert result == {
        'contents': [
            {
                'language': 'python',
                'value': 'class NumberLooper(param start, param end)'
            },
            'Very important class that is capable of gathering all the number strings in [start, end)'
        ]
    }

def test_cross_package_hover():
    uri = "file:///fizzbuzz_service/checkers/fizzbuzz/fizzbuzz_checker.py"
    line, col = 5, 31
    result = fizzbuzz_workspace.hover(uri, line, col)
    assert result == {
        'contents': [
            {
                'language': 'python',
                'value': 'def should_fizz(param number)'
            },
            'Whether or not "fizz" should be printed for this number'
        ]
    }

def test_std_lib_hover():
    uri = "file:///fizzbuzz_service/__main__.py"
    line, col = 5, 10
    result = fizzbuzz_workspace.hover(uri, line, col)
    assert result == {
        'contents': [
            {
                'language': 'python',
                'value': 'def print(param value, param ..., param sep, param '
                                    'end, param file, param flush)'
            },
            "print(value, ..., sep=' ', end='\\n', file=sys.stdout, "
            'flush=False)\n'
            '\n'
            'Prints the values to a stream, or to sys.stdout by default.\n'
            'Optional keyword arguments:\n'
            'file:  a file-like object (stream); defaults to the current '
            'sys.stdout.\n'
            'sep:   string inserted between values, default a space.\n'
            'end:   string appended after the last value, default a newline.\n'
            'flush: whether to forcibly flush the stream.'
        ]
    }

    