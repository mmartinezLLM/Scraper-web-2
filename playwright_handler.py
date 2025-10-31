"""
Módulo para manejar el renderizado de páginas con Playwright.
"""
import os
import logging
from playwright.sync_api import sync_playwright
from urllib.parse import urlparse
import playwright 
# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PlaywrightHandler:
    """Manejador de Playwright para renderizado de páginas dinámicas."""
    
    def __init__(self, headless=True, timeout=60):
        """
        Inicializa el manejador de Playwright.
        
        Args:
            headless (bool): Si se debe ejecutar en modo headless
            timeout (int): Tiempo máximo de espera para cargar la página (en segundos)
        """
        self.headless = headless
        self.timeout = timeout
        self.browser = None
        self.context = None
        self.is_initialized = False
        
    def __enter__(self):
        """Inicializar Playwright al entrar en el contexto."""
        self.initialize()
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Cerrar Playwright al salir del contexto."""
        self.close()
        
    def initialize(self):
        """Inicializar el navegador y contexto de Playwright."""
        if self.is_initialized:
            return
            
        try:
            self.playwright = sync_playwright().start()
            self.browser = self.playwright.chromium.launch(headless=self.headless)
            self.context = self.browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36'
            )
            self.is_initialized = True
            
        except Exception as e:
            logger.error(f"Error inicializando Playwright: {e}")
            self.close()
            raise
            
    def close(self):
        """Cerrar y limpiar recursos de Playwright."""
        try:
            if self.context:
                self.context.close()
            if self.browser:
                self.browser.close()
            if hasattr(self, 'playwright'):
                self.playwright.stop()
        except Exception as e:
            logger.error(f"Error cerrando Playwright: {e}")
        finally:
            self.is_initialized = False
            self.context = None
            self.browser = None
            
    def _should_use_playwright(self, url, content_length=None, content_type=None):
        """
        Determina si una URL debe ser procesada con Playwright.
        
        Args:
            url: URL a analizar
            content_length: Tamaño del contenido (opcional)
            content_type: Tipo de contenido (opcional)
            
        Returns:
            bool: True si se debe usar Playwright
        """
        try:
            # Si el content_type es text/html, siempre usar Playwright
            if content_type and 'text/html' in content_type.lower():
                return True

            # Si no hay content_type, usar las heurísticas anteriores como fallback
            parsed = urlparse(url.lower())
            path = parsed.path

            # Detectar WordPress y otros CMS
            cms_indicators = [
                '/wp-content/', '/wp-includes/', '/wp-admin/', 'wordpress.com', 'wp.com',
                'drupal', 'joomla', 'magento', 'shopify', 'wix.com', 'squarespace'
            ]
            if any(ind in url.lower() for ind in cms_indicators):
                return True

            # Revisar extensión del archivo
            if path.endswith(('.html', '.php', '.aspx', '.jsp')):
                return True

            # Revisar tamaño del contenido
            if content_length is not None:
                try:
                    if int(content_length) < 1000:  # Contenido muy pequeño puede indicar JS
                        return True
                except (ValueError, TypeError):
                    pass

            return False

        except Exception:
            return False
            
    def get_page_content(self, url, wait_for_selectors=None, post_load_wait=0):
        """
        Obtiene el contenido renderizado de una página usando Playwright.
        
        Args:
            url: URL a procesar
            wait_for_selectors: Lista de selectores a esperar (opcional)
            post_load_wait: Tiempo adicional de espera después de carga (en segundos)
            
        Returns:
            tuple: (content, status_code)
        """
        if not self.is_initialized:
            self.initialize()
            
        try:
            page = self.context.new_page()
            response = page.goto(url, wait_until='networkidle', timeout=self.timeout * 1000)
            
            if not response:
                return None, 404
                
            status_code = response.status
            
            # Esperar selectores específicos si se proporcionan
            if wait_for_selectors:
                for selector in wait_for_selectors:
                    try:
                        page.wait_for_selector(selector, timeout=5000)
                    except Exception:
                        logger.warning(f"No se encontró el selector: {selector}")
                        
            # Esperar a que los loaders comunes desaparezcan
            common_loaders = [
                # Selectores comunes de loaders
                '.loader', '#loader', '.loading', '#loading',
                '[class*="loader"]', '[class*="loading"]',
                '.spinner', '#spinner', '[class*="spinner"]',
                '.preloader', '#preloader',
                # Selectores específicos de sitios conocidos
                '.loading-logo',  # viajemos.com
                '.LoadingPage',   # Formato común en React/Next.js
                '#nprogress',     # Next.js progress bar
                '.progress-bar',  # Bootstrap y otros
                '[role="progressbar"]',
                '.MuiCircularProgress-root',  # Material-UI
                '.ant-spin'  # Ant Design
            ]
            
            # Intentar esperar a que desaparezcan los loaders usando una función JS
            try:
                selectors_joined = ','.join(common_loaders)
                # wait_for_function: retorna True cuando no hay loaders visibles
                page.wait_for_function(
                    "selectors => { const els = document.querySelectorAll(selectors); if(!els || els.length===0) return true; return Array.from(els).every(e => { try { const s = window.getComputedStyle(e); return !e.offsetParent || s.display === 'none' || s.visibility === 'hidden' || e.hidden; } catch(err){ return true; } }); }",
                    arg=selectors_joined,
                    timeout=20000,
                )
            except Exception:
                # Si falla la comprobación avanzada, continuamos con un pequeño sleep
                try:
                    page.wait_for_timeout(1500)
                except Exception:
                    pass

            # Esperar un tiempo base para asegurar la carga completa
            try:
                page.wait_for_timeout(2000)  # 2 segundos base
            except Exception:
                pass

            # Esperar tiempo adicional si se especifica
            if post_load_wait > 0:
                try:
                    page.wait_for_timeout(post_load_wait * 1000)
                except Exception:
                    pass

            # Esperar a que no haya peticiones de red pendientes
            try:
                page.wait_for_load_state('networkidle')
            except Exception:
                pass
            
            # Verificar si el contenido principal está visible
            main_content_selectors = [
                'main', '#main', '.main-content', '#content', 
                'article', '.content', '[role="main"]'
            ]
            
            for selector in main_content_selectors:
                try:
                    element = page.wait_for_selector(selector, timeout=5000)
                    if element:
                        # Esperar a que el elemento sea visible
                        element.wait_for_element_state('visible')
                        break
                except Exception:
                    continue
            
            # Obtener contenido
            content = page.content()
            page.close()
            
            return content, status_code
            
        except Exception as e:
            logger.error(f"Error obteniendo contenido con Playwright: {e}")
            return None, 500
            
    def get_page_screenshot(self, url, path=None):
        """
        Toma una captura de pantalla de la página.
        
        Args:
            url: URL a capturar
            path: Ruta donde guardar la captura (opcional)
            
        Returns:
            bytes: Datos de la imagen si path es None, sino None
        """
        if not self.is_initialized:
            self.initialize()
            
        try:
            page = self.context.new_page()
            page.goto(url, wait_until='networkidle', timeout=self.timeout * 1000)
            page.wait_for_load_state('networkidle')
            
            if path:
                page.screenshot(path=path, full_page=True)
                page.close()
                return None
            else:
                screenshot = page.screenshot(full_page=True)
                page.close()
                return screenshot
                
        except Exception as e:
            logger.error(f"Error tomando captura: {e}")
            return None