import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from wizq.paths import Paths
from wizq.storage import Store
from wizq.vault import Vault


@pytest.fixture
def profile(tmp_path):
    paths = Paths(tmp_path / "profile")
    paths.prepare()
    store = Store(paths.database)
    vault = Vault(store)
    vault.initialize("test-master-password")
    yield paths, store, vault
    store.close()
