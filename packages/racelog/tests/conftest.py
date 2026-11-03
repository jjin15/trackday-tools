import pytest

from racelog.testing import make_session, make_slip_session


@pytest.fixture
def session_factory():
    return make_session


@pytest.fixture
def slip_session_factory():
    return make_slip_session
