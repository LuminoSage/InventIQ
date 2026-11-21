import pytest

from inventiq.data import synth
from inventiq.engine import Engine


@pytest.fixture(scope="session")
def data():
    return synth.generate()


@pytest.fixture(scope="session")
def engine():
    return Engine()
