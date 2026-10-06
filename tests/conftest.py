import pytest

from finance.crypto import TokenCipher, generate_key
from finance.db import init_db, make_engine


@pytest.fixture
def engine(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path}/test.db")
    init_db(engine)
    return engine


@pytest.fixture
def cipher():
    return TokenCipher(generate_key())
