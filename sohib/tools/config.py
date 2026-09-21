import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ToolSettings:
    mode: str = 'disabled'
    connection_file: str = ''
    profile: str = ''

    def __post_init__(self):
        if self.mode not in {'disabled', 'fixture', 'browser'}:
            raise ValueError(
                'STOCKBIT_MODE must be disabled, fixture, or browser for tool service.'
            )

    @classmethod
    def load(cls):
        from ..onboarding import home, read_config

        saved = read_config() or {}
        # Environment overrides saved setup; saved setup overrides the private default home.
        root = home()
        return cls(
            os.getenv('STOCKBIT_MODE', 'browser' if saved else 'disabled'),
            str(
                Path(
                    os.getenv('STOCKBIT_BROWSER_CONNECTION_FILE')
                    or saved.get('connection_file')
                    or root / 'browser.json'
                ).resolve()
            ),
            str(
                Path(
                    os.getenv('STOCKBIT_BROWSER_PROFILE') or saved.get('profile') or root / 'chrome'
                ).resolve()
            ),
        )
