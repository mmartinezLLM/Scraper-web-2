"""
Módulo para manejar el renderizado de páginas con Playwright.
"""
import os
import logging
import queue
import time
from playwright.sync_api import sync_playwright
from urllib.parse import urlparse
import threading

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PlaywrightHandler:
    """Manejador de Playwright para renderizado de páginas dinámicas."""
    
    def __init__(self, headless=True, timeout=30):
        """
        Inicializa el manejador de Playwright.
        
        Args:
            headless (bool): Si se debe ejecutar en modo headless
            timeout (int): Tiempo máximo de espera para cargar la página (en segundos, default 30)
        """
        self.headless = headless
        self.timeout = timeout
        self.browser = None
        self.context = None
        self.is_initialized = False
        # Límite de páginas concurrentes manejadas por Playwright (aumentado para paralelismo)
        self.max_concurrent_pages = 8
        self._page_semaphore = threading.Semaphore(self.max_concurrent_pages)
        # Pool de páginas reutilizables para reciclado inteligente
        self._page_pool = queue.Queue(maxsize=self.max_concurrent_pages)
        # Número de reintentos en navegación (reducido para performance)
        self.nav_retries = 1
        # Backoff base en segundos (reducido)
        self.nav_backoff = 0.5
        
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
                ignore_https_errors=True,  # NUEVO: Permitir certificados SSL inválidos
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36'
            )
            # Precrear un pequeño pool de páginas para reciclar
            try:
                for _ in range(self.max_concurrent_pages):
                    p = self.context.new_page()
                    # Navegar a about:blank para tener una página limpia
                    try:
                        p.goto('about:blank', timeout=5000)
                    except Exception:
                        pass
                    self._page_pool.put(p)
            except Exception:
                # Si falla la creación del pool, vaciar cualquier página parcial
                while not self._page_pool.empty():
                    try:
                        page = self._page_pool.get_nowait()
                        try:
                            page.close()
                        except Exception:
                            pass
                    except Exception:
                        break

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
            if content_type and 'text/html' in content_type.lower():
                return True

            parsed = urlparse(url.lower())
            path = parsed.path

            cms_indicators = [
                '/wp-content/', '/wp-includes/', '/wp-admin/', 'wordpress.com', 'wp.com',
                'drupal', 'joomla', 'magento', 'shopify', 'wix.com', 'squarespace'
            ]
            if any(ind in url.lower() for ind in cms_indicators):
                return True

            if path.endswith(('.html', '.php', '.aspx', '.jsp')):
                return True

            if content_length is not None:
                try:
                    if int(content_length) < 1000:
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
        # Control de concurrencia: intentar adquirir permiso para abrir/usar una página
        acquired = False
        try:
            acquired = self._page_semaphore.acquire(timeout=30)
        except Exception:
            acquired = False

        if not acquired:
            logger.warning(f"No se pudo adquirir permiso para abrir página (timeout): {url}")

        if not self.is_initialized:
            self.initialize()

        page = None
        content = None
        status_code = 500

        try:
            # Obtener una página del pool (reutilizable)
            try:
                page = self._page_pool.get(timeout=20)
            except Exception:
                # Si no hay página en el pool, crear una nueva de forma segura
                try:
                    page = self.context.new_page()
                except Exception as e:
                    logger.error(f"No se pudo crear una nueva página: {e}")
                    return None, 500

            # Intentar la navegación con reintentos y backoff (OPTIMIZADO)
            response = None
            last_exc = None
            for attempt in range(1, self.nav_retries + 2):
                try:
                    # Cambio: usar 'load' en lugar de 'networkidle' para rendimiento
                    # 'load' espera event DOMContentLoaded + carga de recursos principales
                    response = page.goto(url, wait_until='load', timeout=self.timeout * 1000)
                    # si navegó sin excepción, romper
                    break
                except Exception as e:
                    last_exc = e
                    logger.debug(f"⚠️ Intento {attempt} - error en load ({url}): {e}")
                    # reintentar con domcontentloaded una sola vez
                    if attempt == 1:
                        try:
                            response = page.goto(url, wait_until='domcontentloaded', timeout=15000)
                            logger.debug(f"✔️ Reintento con domcontentloaded exitoso ({url})")
                            break
                        except Exception as e2:
                            last_exc = e2
                            logger.debug(f"Fallo domcontentloaded: {e2}")
                    # esperar backoff mínimo antes del siguiente intento
                    if attempt <= self.nav_retries:
                        time.sleep(self.nav_backoff * 0.5)

            if not response:
                logger.error(f"Navegación fallida tras {self.nav_retries + 1} intentos: {last_exc}")
                return None, 500

            status_code = response.status

            # OPTIMIZADO: Esperar solo selectores críticos (reducidos de 7 a 2)
            if wait_for_selectors:
                # Priorizar solo selectores críticos para análisis SEO
                critical_selectors = [sel for sel in wait_for_selectors if sel in ['h1', 'title', 'meta[name="description"]']]
                for selector in critical_selectors[:2]:  # Máximo 2 selectores
                    try:
                        page.wait_for_selector(selector, timeout=2000)
                    except Exception:
                        logger.debug(f"No se encontró el selector: {selector}")

            # OPTIMIZADO: Reducida de 2000ms a 500ms - solo para permitir JS mínimo
            try:
                page.wait_for_timeout(500)
            except Exception:
                pass

            # OPTIMIZADO: Eliminada espera post_load_wait por defecto (no requerida)
            # Solo incluida si es realmente necesaria para casos especiales
            if post_load_wait and post_load_wait > 2:
                try:
                    page.wait_for_timeout(min(post_load_wait * 1000, 3000))  # Máximo 3 segundos
                except Exception:
                    pass

            # ELIMINADA: Detección de contenido principal - innecesaria para análisis SEO rápido
            # El contenido está disponible tras 'load' event

            # Obtener el HTML resultante
            try:
                content = page.content()
            except Exception as e:
                logger.warning(f"No se pudo obtener contenido de la página ({url}): {e}")

            if not content or not str(content).strip():
                logger.warning(f"⚠️ HTML vacío tras renderizado: {url}")

            return content, status_code

        except Exception as e:
            logger.error(f"Error obteniendo contenido con Playwright: {e}")
            return None, 500
        finally:
            # En lugar de cerrar la página, intentar dejarla en estado reutilizable y devolver al pool
            try:
                if page:
                    try:
                        # OPTIMIZADO: Reset más rápido - solo limpiar sin navegar
                        # (about:blank añade latencia innecesaria)
                        page.evaluate('() => window.location.href = "about:blank"')
                    except Exception:
                        try:
                            page.close()
                            # reemplazar la página al crear una nueva
                            page = self.context.new_page()
                        except Exception:
                            page = None
                    # Devolver al pool si la página es válida
                    if page:
                        try:
                            self._page_pool.put_nowait(page)
                        except Exception:
                            try:
                                page.close()
                            except Exception:
                                pass
            except Exception:
                pass
            # Liberar el semáforo si lo adquirimos
            try:
                if acquired:
                    self._page_semaphore.release()
            except Exception:
                pass
            
    def get_page_screenshot(self, url, path=None):
        """
        Toma una captura de pantalla de la página.
        
        Args:
            url: URL a capturar
            path: Ruta donde guardar la captura (opcional)
            
        Returns:
            bytes: Datos de la imagen si path es None, sino None
        """
        # Control de concurrencia similar a get_page_content
        acquired = False
        try:
            acquired = self._page_semaphore.acquire(timeout=30)
        except Exception:
            acquired = False

        if not acquired:
            logger.warning(f"No se pudo adquirir permiso para captura de página (timeout): {url}")

        if not self.is_initialized:
            self.initialize()

        page = None
        try:
            try:
                page = self._page_pool.get(timeout=20)
            except Exception:
                page = self.context.new_page()

            # Reintentos simples para la navegación
            last_exc = None
            for attempt in range(1, self.nav_retries + 2):
                try:
                    page.goto(url, wait_until='networkidle', timeout=self.timeout * 1000)
                    break
                except Exception as e:
                    last_exc = e
                    logger.warning(f"Intento {attempt} para screenshot falló: {e}")
                    if attempt <= self.nav_retries:
                        time.sleep(self.nav_backoff * attempt)

            if last_exc and not page:
                logger.error(f"No se pudo obtener página para screenshot: {last_exc}")
                return None

            # Asegurar carga mínima
            try:
                page.wait_for_load_state('networkidle')
            except Exception:
                pass

            if path:
                page.screenshot(path=path, full_page=True)
                return None
            else:
                screenshot = page.screenshot(full_page=True)
                return screenshot

        except Exception as e:
            logger.error(f"Error tomando captura: {e}")
            return None
        finally:
            try:
                if page:
                    try:
                        page.goto('about:blank', timeout=5000)
                    except Exception:
                        try:
                            page.close()
                        except Exception:
                            pass
                    try:
                        self._page_pool.put_nowait(page)
                    except Exception:
                        try:
                            page.close()
                        except Exception:
                            pass
            except Exception:
                pass
            try:
                if acquired:
                    self._page_semaphore.release()
            except Exception:
                pass
