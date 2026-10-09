"""Copy/compile the read-only indicator in the configured demo terminal."""
import shutil
import subprocess
from pathlib import Path

import MetaTrader5 as mt5
from config import load_settings
from main import initialize_mt5, verify_account


def main():
    settings = load_settings()
    initialize_mt5(settings)
    try:
        verify_account(settings)
        info = mt5.terminal_info()
        if info is None:
            raise RuntimeError('MT5 terminal information unavailable')
        source = Path(__file__).resolve().parents[2] / 'mt5' / 'Indicators' / 'TradingBotShadow.mq5'
        folder = Path(info.data_path) / 'MQL5' / 'Indicators' / 'TradingBot'
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / source.name
        shutil.copyfile(source, target)
        print(f'Indicator source installed: {target}')
        editor = Path(settings.mt5_terminal_path).parent / 'metaeditor64.exe'
        log = target.with_suffix('.log')
        binary = target.with_suffix('.ex5')
        if not editor.exists():
            print('MetaEditor not found. Open the installed source in MT5 MetaEditor and press F7.')
            return
        # Keep a previous binary as a fallback, but never report it as a new compile.
        previous_mtime = binary.stat().st_mtime_ns if binary.exists() else None
        result = subprocess.run([str(editor), f'/compile:{target}', '/log'], timeout=120)
        changed = binary.exists() and binary.stat().st_mtime_ns != previous_mtime
        if not changed:
            print(f'Compilation not confirmed (exit={result.returncode}). Open MetaEditor and press F7.')
            print(f'Compiler log: {log}')
            if log.exists():
                data = log.read_bytes()
                encoding = 'utf-16' if data.startswith((b'\xff\xfe', b'\xfe\xff')) else 'utf-8'
                print(data.decode(encoding, errors='replace')[-4000:])
            return
        print(f'Compiled indicator: {binary}')
        print('In MT5: Navigator > Indicators > TradingBot > TradingBotShadow; drag onto an M5 chart.')
        print('If missing, right-click Indicators > Refresh. Algo Trading can remain OFF.')
    finally:
        mt5.shutdown()


if __name__ == '__main__':
    main()
