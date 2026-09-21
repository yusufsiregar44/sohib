import argparse
import json

from .catalogue import catalogue
from .config import ToolSettings
from .service import ToolService


def main():
    parser = argparse.ArgumentParser(description='SohiB research tools; no model configuration')
    parser.add_argument('command', choices=['catalogue', 'call'])
    parser.add_argument('--name')
    parser.add_argument('--arguments', default='{}')
    args = parser.parse_args()
    settings = ToolSettings.load()
    if args.command == 'catalogue':
        result = catalogue(settings.mode)
    else:
        try:
            arguments = json.loads(args.arguments)
        except ValueError:
            arguments = None
        result = ToolService(settings).call(args.name, arguments)
    print(json.dumps(result, indent=2))
    return 1 if result.get('status') == 'error' else 0


if __name__ == '__main__':
    raise SystemExit(main())
