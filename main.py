import argparse
import os
import sys
import time
import traceback
import tkinter as tk
from pathlib import Path

try:
    from src.core.seo_analyzer import SEOAnalyzer
    from src.ui.gui import SEOSpiderGUI
except ImportError as e:
    print(f"❌ Error importando módulos: {e}")
    print("Verifica que estás en el directorio correcto y que src/ está en PYTHONPATH")
    sys.exit(1)


def make_printer(analyzer):
    def _printer(msg, data=None):
        ts = time.strftime('%H:%M:%S')
        print(f"[{ts}] {msg}")
        if data:
            visited = data.get('completed')
            pending = len(analyzer.to_visit) if analyzer else 'N/A'
            print(f"    Visited: {visited} | Pending: {pending}")
    return _printer


def run_gui():
    """Launch the GUI using the new modular structure."""
    try:
        root = tk.Tk()
        
        # Configurar el icono de la aplicación
        try:
            # Obtener la ruta absoluta del directorio actual
            current_dir = os.path.dirname(os.path.abspath(__file__))
            icon_path = os.path.join(current_dir, 'scraper.ico')
            
            # Intentar cargar el icono
            if os.path.exists(icon_path):
                root.iconbitmap(icon_path)
            else:
                print(f"⚠️ No se encontró el archivo de icono en: {icon_path}")
        except Exception as icon_error:
            print(f"⚠️ No se pudo cargar el icono: {icon_error}")
        
        app = SEOSpiderGUI(root)
        root.mainloop()
        return 0
    except Exception as e:
        print(f"❌ Error al iniciar la interfaz gráfica: {e}")
        traceback.print_exc()
        return 1


def run_test_script():
    """Run the test runner script."""
    import subprocess
    test_file = Path('test_run.py')
    if not test_file.exists():
        print("❌ test_run.py not found in project root.")
        return 1
    print(f"Running test runner {test_file}...")
    return subprocess.call([sys.executable, str(test_file)])


def run_crawl(url, max_pages, delay, force, headless, wait, save_report):
    if SEOAnalyzer is None:
        print("❌ Could not import SEOAnalyzer from src.core.seo_analyzer. Check PYTHONPATH or package layout.")
        return 1

    analyzer = SEOAnalyzer(url, max_pages=max_pages, delay=delay, force_playwright=force, headless_mode=headless, post_load_wait=wait)
    printer = make_printer(analyzer)

    print(f"Starting crawl: {url} (max_pages={max_pages}, delay={delay}, force_playwright={force}, headless={headless}, wait={wait})")
    try:
        analyzer.crawl_site(progress_callback=printer)
    except Exception as e:
        print("❌ Crawl failed with exception:")
        traceback.print_exc()
        return 1

    print('\nCrawl finished')
    print('Pages visited:', len(analyzer.visited))
    print('Broken links found:', len(analyzer.broken_links))

    if save_report:
        print('Generating report...')
        fname = analyzer.generate_report(progress_callback=printer)
        if fname:
            print('Report saved to', fname)
        else:
            print('Report generation skipped or failed.')

    return 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Main runner for Scraper Web project')
    parser.add_argument('--mode', choices=['gui', 'crawl', 'test'], default='gui', help='Mode to run')

    # Crawl options
    parser.add_argument('--url', default='https://example.com', help='Base URL for crawling')
    parser.add_argument('--max-pages', type=int, default=1, help='Max pages to crawl (default: 1 = unlimited)')
    parser.add_argument('--delay', type=float, default=0.5, help='Delay between requests')
    parser.add_argument('--force', action='store_true', help='Force Playwright render for every page')
    parser.add_argument('--no-headless', action='store_false', dest='headless', help='Run Playwright with browser visible (default: headless)', default=True)
    parser.add_argument('--wait', type=float, default=0.0, help='Extra seconds to wait after page load (for challenges)')
    parser.add_argument('--save-report', action='store_true', help='Generate Excel report after crawl')

    args = parser.parse_args()

    if args.mode == 'gui':
        sys.exit(run_gui())
    elif args.mode == 'test':
        sys.exit(run_test_script())
    else:
        sys.exit(run_crawl(args.url, args.max_pages, args.delay, args.force, args.headless, args.wait, args.save_report))
