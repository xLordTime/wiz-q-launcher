# Third-party inventory
- Deimos wizlaunch source: Deimos contributors, GPL-3.0-only, pinned to 99194d7d053b011f2db36bcc2d2bf6635acb7d7e. Included under native/, full source and license provided.
- Original Wiz Q Launcher portions: MIT, original notice retained in LICENSE-MIT.
- PySide6/Qt: Qt project, GPL/LGPL/commercial options; combined distribution uses GPL-compatible licensing. Official source and licensing: https://code.qt.io/pyside/pyside-setup.git and https://www.qt.io/licensing/.
- cryptography: Apache-2.0 OR BSD-3-Clause; https://github.com/pyca/cryptography
- psutil: BSD-3-Clause; https://github.com/giampaolo/psutil
- requests: Apache-2.0; https://github.com/psf/requests
- packaging: Apache-2.0 OR BSD-2-Clause; https://github.com/pypa/packaging
- pypresence: MIT; https://github.com/qwertyquerty/pypresence
- FFmpeg is an external user-selected executable, not silently downloaded or redistributed. Its license depends on its build, especially libx264: https://ffmpeg.org/legal.html

Exact Python versions are in requirements.txt. Native dependency versions are pinned in Cargo.toml; the release build's resolved transitive Cargo lock is retained when generated. No copyrighted game assets or passwords are embedded in the launcher themes.
