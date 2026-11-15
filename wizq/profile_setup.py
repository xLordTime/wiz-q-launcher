"""Create a separate local profile and make it the default after setup succeeds."""

from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

from packaging.version import Version

from . import __version__
from .paths import DEFAULT_PROFILE_MARKER, Paths
from .storage import Store, check_database
from .vault import Vault


def new_profile_destination():
    paths = Paths.new_local()
    if paths.root.exists() or paths.root.is_symlink() or paths.root.is_junction():
        raise ValueError(f"Unter {paths.root} gibt es bereits einen Ordner oder eine Datei.")
    return paths


def create_new_local_profile(password):
    destination = new_profile_destination()
    destination.root.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".wizq-profile-", dir=destination.root.parent) as temporary:
        staged = Paths(Path(temporary) / destination.root.name)
        staged.prepare()
        with closing(Store(staged.database)) as store, store.transaction():
            Vault(store).initialize(password)
            store.set("migration_checked", True, meta=True)
            if Version(__version__).is_prerelease:
                store.set("update_channel", "beta")
        check_database(staged.database, full=True)
        (staged.root / DEFAULT_PROFILE_MARKER).touch(exist_ok=False)
        # Publish only a complete profile. On Windows rename requires a free destination.
        if destination != new_profile_destination():
            raise RuntimeError("Der Speicherort für das neue Profil hat sich geändert.")
        staged.root.rename(destination.root)
    return destination
