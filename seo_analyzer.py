"""
Módulo principal del analizador SEO - VERSIÓN SIMPLIFICADA
Contiene la lógica básica de análisis y rastreo de sitios web.
"""

import os
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from collections import deque
import time
import pandas as pd
from datetime import datetime
import logging
from tkinter import filedialog
from .playwright_handler import PlaywrightHandler
import urllib3
import concurrent.futures
import math

# Suprimir advertencias de SSL cuando intentionalmente usamos verify=False
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Funciones helper para detección inteligente
def is_cloudflare_challenge(html_content, status_code):
    """
    Detecta si la respuesta es un challenge de Cloudflare.
    Estos sitios requieren Playwright para bypasear protección.
    """
    # Signos de Cloudflare challenge
    if status_code == 403:
        return True
    
    if html_content and "Enable JavaScript and cookies to continue" in html_content:
        return True
    
    if html_content and "Just a moment..." in html_content:
        return True
    
    if html_content and "Checking your browser before accessing" in html_content:
        return True
    
    return False


def is_skeleton_html(html_content):
    """
    Detecta si el HTML es un skeleton (SPA sin contenido real).
    Estos sitios renderzan contenido con JavaScript, requieren Playwright.
    """
    if not html_content or len(html_content.strip()) < 100:
        return False
    
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Contar elementos significativos
    try:
        headings = len(soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6']))
        paragraphs = len(soup.find_all('p'))
        text_length = len(soup.get_text(strip=True))
        
        # SPA skeleton: pocos headings/párrafos pero HTML voluminoso
        # Ej: viajemos.com tiene 21KB de HTML pero 0 caracteres de texto
        if text_length < 50 and len(html_content) > 1000:
            logger.debug(f"🔍 Detectado skeleton HTML: {len(html_content)} bytes HTML pero solo {text_length} chars texto")
            return True
        
        # Si tiene muy poco contenido extraible: probablemente SPA
        if text_length < 100 and headings == 0:
            logger.debug(f"🔍 Detectado skeleton HTML: sin headings y {text_length} chars texto")
            return True
            
    except Exception as e:
        logger.debug(f"Error al analizar skeleton HTML: {e}")
    
    return False


def validate_extraction(soup):
    """
    Valida si BeautifulSoup logró extraer contenido significativo.
    Si falla, indica que se necesita Playwright (contenido dinámico).
    """
    if not soup:
        return False
    
    try:
        title = soup.find('title')
        h1s = soup.find_all('h1')
        text_length = len(soup.get_text(strip=True))
        
        # Si no tiene título O no tiene H1 O tiene muy poco texto = extracción falló
        if not title or not h1s or text_length < 50:
            logger.debug(f"⚠️  Extracción débil: title={bool(title)}, h1={len(h1s)}, texto={text_length}")
            return False
        
        return True
    except Exception as e:
        logger.debug(f"Error al validar extracción: {e}")
        return False


class SEOAnalyzer:
    """Analizador SEO para sitios web."""
    
    def __init__(self, base_url, max_pages=1, delay=1, specific_urls=None, analyze_images=True, analyze_links=True, headless_mode=False):
        """
        Inicializa el analizador SEO.
        
        Args:
            base_url (str): URL base para comenzar el análisis
            max_pages (int): Número máximo de páginas a analizar (default: 1 = sin límite)
            delay (float): Tiempo de espera entre requests
            specific_urls (list): Lista de URLs específicas a analizar (opcional)
            analyze_images (bool): Si se deben analizar las imágenes
            analyze_links (bool): Si se deben analizar los enlaces
        """
        self.base_url = base_url
        self.max_pages = max_pages
        self.delay = delay
        self.analyze_images = analyze_images
        self.analyze_links = analyze_links
        self.headless_mode = headless_mode
        
        # Colecciones de datos
        self.visited = set()
        self.to_visit = deque(specific_urls if specific_urls else [base_url])
        self.specific_urls = set(specific_urls) if specific_urls else None
        self.results = []
        self.is_running = True
        self.start_time = None
        
        # Estado de pausa/resumen
        self.is_paused = False
        self.current_state = {}  # Para guardar el estado durante pausas
        
        # Colecciones para detectar duplicados
        self.meta_titles = {}  # {titulo: [urls]}
        self.h1s = {}         # {h1: [urls]}
        self.meta_desc = {}   # {descripcion: [urls]}
        
        # Colección para imágenes
        self.images = []      # Lista de diccionarios con datos de imágenes
        
        # Colección para enlaces
        self.links = []      # Lista de diccionarios con datos de enlaces
        # Estado de enlaces rotos y redirecciones
        self.broken_links = []
        self.redirected_urls = []

        # Handler de Playwright (reutilizable para evitar abrir múltiples navegadores)
        self.playwright_handler = None

        # Cache de estado de URLs para evitar HEAD/GET duplicados
        # key: url -> value: status_code (int) or special codes like 'ERROR', 'TIMEOUT'
        self.url_status_cache = {}
        # Circuit breaker por dominio: {domain: {'fails': int, 'last_fail_ts': float, 'open_until': float}}
        self.domain_failures = {}
        self.circuit_failure_threshold = 3
        self.circuit_cooldown = 60  # seconds to keep circuit open after threshold exceeded

        # Retry policy for requests
        self.request_max_retries = 2
        self.request_backoff_base = 0.8
        
        # Configurar sesión de requests
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'es-ES,es;q=0.9,en;q=0.8',
        })
    
    def is_same_domain(self, url1, url2):
        """Compara si dos URLs pertenecen al mismo dominio.""" 
        try:
            parsed1 = urlparse(url1.lower())
            parsed2 = urlparse(url2.lower())
            domain1 = parsed1.netloc.replace('www.', '')
            domain2 = parsed2.netloc.replace('www.', '')
            return domain1 == domain2
        except Exception:
            return False

    def _normalize_url(self, url):
        """Normaliza una URL removiendo fragmentos y espacios innecesarios."""
        try:
            parsed = urlparse(url)
            # Reconstruir sin fragmento
            normalized = parsed._replace(fragment='').geturl()
            return normalized
        except Exception:
            return url

    def is_valid_url(self, url):
        """Valida si una URL debe ser analizada.
        
        Lógica simplificada y clara:
        - Si hay specific_urls: SOLO permitir URLs en esa lista
        - Si NO hay specific_urls: SOLO permitir URLs del mismo dominio
        - Rechazar extensiones/protocolos no válidos en ambos casos
        """
        try:
            # ✅ PRIMERO: Verificar extensiones/protocolos (aplicar ANTES de cualquier otra cosa)
            invalid_protocols = ['mailto:', 'tel:', 'javascript:', 'data:']
            if any(url.lower().startswith(proto) for proto in invalid_protocols):
                logger.debug(f"is_valid_url: protocolo inválido: {url}")
                return False
            
            excluded_extensions = [
                # Imágenes y documentos
                '.pdf', '.jpg', '.jpeg', '.png', '.gif', '.ico', '.svg', '.webp',
                # Recursos web
                '.css', '.js', '.json', '.xml', '.txt',
                # Fuentes
                '.woff', '.woff2', '.ttf', '.eot', '.otf',
                # Media
                '.mp3', '.mp4', '.wav', '.ogg', '.webm',
                # Recursos estáticos
                '.map'
            ]
            
            if any(url.lower().endswith(ext) for ext in excluded_extensions):
                # Si es una imagen, agregarla a la lista de imágenes pero no analizarla
                if any(url.lower().endswith(img_ext) for img_ext in ['.jpg', '.jpeg', '.png', '.gif', '.ico', '.svg', '.webp']):
                    if self.analyze_images:
                        img_data = {
                            'Pagina Origen': url,
                            'URL Imagen': url,
                            'Title': '',
                            'Alt': '',
                            'Tipo Imagen': url.split('.')[-1].upper(),
                            'Peso': '0 KB',
                            'Estado': 'No verificado'
                        }
                        self.images.append(img_data)
                logger.debug(f"is_valid_url: extensión excluida: {url}")
                return False
            
            # Verificar patrones de recursos estáticos
            static_patterns = [
                '/_next/static/',
                '/static/',
                '/assets/',
                '/dist/',
                '/build/',
                '/themes/'
            ]
            if any(pattern in url.lower() for pattern in static_patterns):
                logger.debug(f"is_valid_url: patrón estático detectado: {url}")
                return False
            
            # ✅ SEGUNDO: Parsear y verificar dominio (aplicar DESPUÉS de descartar extensiones/protocolos)
            parsed = urlparse(url)
            
            # Si la URL no tiene netloc (p.ej. es relativa), permitir
            # (será normalizada en add_url_to_queue)
            if not parsed.netloc:
                return True
            
            # Modo 1: URLs específicas (lista blanca)
            if self.specific_urls is not None:
                # SOLO permitir si está en la lista explícita
                if url not in self.specific_urls:
                    logger.debug(f"is_valid_url: URL no en lista específica: {url}")
                    return False
            else:
                # Modo 2: Crawling general (SOLO mismo dominio)
                if not self.is_same_domain(url, self.base_url):
                    logger.debug(f"is_valid_url: dominio distinto al base_url: {url}")
                    return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error en is_valid_url({url}): {e}")
            return False
            
    def add_url_to_queue(self, url):
        """Añade una URL a la cola si cumple los criterios básicos.
        
        NOTA: No realiza validación HEAD/GET aquí. La validación de contenido
        se realiza en crawl_page() cuando se procesa la URL. Esto permite
        descubrir URLs internas y hreflangs sin bloquearlas prematuramente.
        """
        try:
            # Normalizar rutas relativas respecto a la base_url si es necesario
            parsed = urlparse(url)
            if not parsed.netloc and self.base_url:
                url = urljoin(self.base_url, url)

            url = self._normalize_url(url)
            
            # Rechazar si ya fue visitada o ya está en cola
            if url in self.visited or url in self.to_visit:
                return False

            # Verificar circuito por dominio (evitar hammering a dominios con fallos repetidos)
            domain = urlparse(url).netloc.replace('www.', '')
            if self._is_circuit_open(domain):
                logger.debug(f"Circuit open for domain {domain}, saltando {url}")
                return False

            # Si ya consultamos el estado de esta URL y fue error, no añadir
            cached = self.url_status_cache.get(url)
            if cached is not None:
                try:
                    if isinstance(cached, int) and cached >= 400:
                        # URL está en caché como error (≥400), no la añadimos
                        logger.debug(f"add_url_to_queue: URL en caché con error {cached}: {url}")
                        return False
                    elif isinstance(cached, int) and cached < 400:
                        # URL está en caché como exitosa, agregar a la cola
                        self.to_visit.append(url)
                        logger.debug(f"add_url_to_queue: URL en caché como exitosa: {url}")
                        return True
                except Exception:
                    pass

            # Validar URL básica (extensión, protocolo, dominio)
            if not self.is_valid_url(url):
                logger.debug(f"add_url_to_queue: URL descartada por is_valid_url: {url}")
                return False

            # ✅ SIMPLIFICACIÓN: Agregar directamente a la cola sin HEAD/GET
            # La validación de contenido ocurre en crawl_page()
            self.to_visit.append(url)
            logger.debug(f"add_url_to_queue: URL añadida a la cola: {url}")
            return True

        except Exception as e:
            logger.error(f"Error en add_url_to_queue({url}): {e}")
            return False

        return False

    def _check_link_status(self, url):
        """Verifica el estado de un enlace y retorna su información."""
        # Reusar resultado si ya lo tenemos en cache para evitar peticiones duplicadas
        try:
            cached = self.url_status_cache.get(url)
            if cached is not None:
                if isinstance(cached, int):
                    if cached == 200:
                        return {'status': 'OK', 'code': 200}
                    elif 300 <= cached < 400:
                        try:
                            self.redirected_urls.append({'url': url, 'code': cached})
                        except Exception:
                            pass
                        return {'status': 'Redirigido', 'code': cached}
                    elif cached == 404:
                        try:
                            self.broken_links.append({'url': url, 'code': 404})
                        except Exception:
                            pass
                        return {'status': 'No encontrado', 'code': 404}
                    else:
                        try:
                            self.broken_links.append({'url': url, 'code': cached})
                        except Exception:
                            pass
                        return {'status': f'Error ({cached})', 'code': cached}
                else:
                    # cached contains a special code string
                    try:
                        self.broken_links.append({'url': url, 'code': cached})
                    except Exception:
                        pass
                    return {'status': f'Error ({cached})', 'code': cached}
        except Exception:
            pass
        try:
            # Circuit breaker check per domain
            domain = urlparse(url).netloc.replace('www.', '')
            if self._is_circuit_open(domain):
                return {'status': 'Circuit Open', 'code': 'CIRCUIT_OPEN'}

            # Request HEAD primero (más rápido) usando política de reintentos
            response = self._request_with_retry('head', url, timeout=10, allow_redirects=True)

            # Si es 405 (Method Not Allowed), intentar con GET
            if getattr(response, 'status_code', None) == 405:
                response = self._request_with_retry('get', url, timeout=10, allow_redirects=True)

            code = getattr(response, 'status_code', None)
            if code == 200:
                self._record_success(domain)
                return {'status': 'OK', 'code': 200}
            elif code is not None and 300 <= code < 400:
                # Registrar redirecciones para seguimiento
                try:
                    self.redirected_urls.append({'url': url, 'code': code})
                except Exception:
                    pass
                self._record_success(domain)
                return {'status': 'Redirigido', 'code': code}
            elif code == 404:
                try:
                    self.broken_links.append({'url': url, 'code': 404})
                except Exception:
                    pass
                self._record_failure(domain)
                return {'status': 'No encontrado', 'code': 404}
            else:
                try:
                    self.broken_links.append({'url': url, 'code': code})
                except Exception:
                    pass
                # Registrar fallo parcial
                self._record_failure(domain)
                return {'status': f'Error ({code})', 'code': code}
                
        except requests.exceptions.SSLError:
            try:
                self.broken_links.append({'url': url, 'code': 'SSL_ERROR'})
            except Exception:
                pass
            return {'status': 'Error SSL', 'code': 'SSL_ERROR'}
        except requests.exceptions.ConnectionError:
            try:
                self.broken_links.append({'url': url, 'code': 'CONN_ERROR'})
            except Exception:
                pass
            return {'status': 'Error de conexión', 'code': 'CONN_ERROR'}
        except requests.exceptions.Timeout:
            try:
                self.broken_links.append({'url': url, 'code': 'TIMEOUT'})
            except Exception:
                pass
            return {'status': 'Timeout', 'code': 'TIMEOUT'}
        except Exception as e:
            try:
                self.broken_links.append({'url': url, 'code': 'ERROR', 'error': str(e)})
            except Exception:
                pass
            return {'status': f'Error: {str(e)}', 'code': 'ERROR'}

    # --- Retry and circuit-breaker helpers ---
    def _is_circuit_open(self, domain):
        """Return True if the circuit is open for a domain."""
        try:
            info = self.domain_failures.get(domain)
            if not info:
                return False
            open_until = info.get('open_until')
            if open_until and time.time() < open_until:
                return True
            return False
        except Exception:
            return False

    def _record_failure(self, domain):
        """Record a failure for a domain and open circuit if threshold exceeded."""
        try:
            now = time.time()
            info = self.domain_failures.get(domain) or {'fails': 0, 'last_fail_ts': 0, 'open_until': 0}
            info['fails'] = info.get('fails', 0) + 1
            info['last_fail_ts'] = now
            if info['fails'] >= self.circuit_failure_threshold:
                info['open_until'] = now + self.circuit_cooldown
            self.domain_failures[domain] = info
        except Exception:
            pass

    def _record_success(self, domain):
        """Reset failure count for a domain on success."""
        try:
            if domain in self.domain_failures:
                self.domain_failures.pop(domain, None)
        except Exception:
            pass

    def _request_with_retry(self, method, url, **kwargs):
        """Perform a requests call with simple retry/backoff and update caches/records.

        Returns the requests.Response or raises the last exception.
        """
        last_exc = None
        for attempt in range(0, self.request_max_retries + 1):
            try:
                if method.lower() == 'head':
                    resp = self.session.head(url, **kwargs)
                else:
                    resp = self.session.get(url, **kwargs)
                return resp
            except Exception as e:
                last_exc = e
                # simple backoff
                try:
                    time.sleep(self.request_backoff_base * (1 + attempt))
                except Exception:
                    pass
        # after retries, raise the last exception
        raise last_exc
            
    def _analyze_image(self, img, page_url):
        """Analiza una imagen y retorna sus características."""
        try:
            # Obtener URL de la imagen
            img_src = img.get('src') or img.get('data-src') or img.get('data-lazy-src')
            if not img_src:
                return None
            
            # Convertir a URL absoluta
            img_url = urljoin(page_url, img_src)
            
            image_data = {
                'Pagina Origen': page_url,
                'URL Imagen': img_url,
                'Title': img.get('title', ''),
                'Alt': img.get('alt', ''),
                'Tipo Imagen': 'Desconocido',
                'Peso': '0 KB',
                'Estado': 'No funcional'
            }
            
            # Determinar tipo de imagen y verificar estado
            try:
                # Intentar HEAD request primero (más rápido)
                response = self.session.head(img_url, timeout=5, allow_redirects=True)
                content_type = response.headers.get('content-type', '').lower()
                
                if response.status_code == 200:
                    image_data['Estado'] = 'Funcional'
                    
                    # Determinar tipo de imagen
                    if 'image/' in content_type:
                        image_data['Tipo Imagen'] = content_type.split('/')[-1].split(';')[0].upper()
                    else:
                        # Intentar por extensión de archivo
                        ext = os.path.splitext(img_url.lower())[1].lstrip('.')
                        if ext in ['jpg', 'jpeg', 'png', 'gif', 'webp', 'svg', 'avif']:
                            image_data['Tipo Imagen'] = ext.upper()
                    
                    # Obtener peso
                    content_length = response.headers.get('content-length')
                    if content_length:
                        size_bytes = int(content_length)
                        if size_bytes < 1024:
                            image_data['Peso'] = f"{size_bytes} B"
                        elif size_bytes < 1024*1024:
                            image_data['Peso'] = f"{size_bytes/1024:.1f} KB"
                        else:
                            image_data['Peso'] = f"{size_bytes/(1024*1024):.1f} MB"
                
            except Exception:
                # Si falla el HEAD, intentar determinar tipo por URL
                ext = os.path.splitext(img_url.lower())[1].lstrip('.')
                if ext in ['jpg', 'jpeg', 'png', 'gif', 'webp', 'svg', 'avif']:
                    image_data['Tipo Imagen'] = ext.upper()
            
            return image_data
            
        except Exception:
            return None

    def crawl_page(self, url, progress_callback=None):
        """Analiza una página web independientemente de su tipo."""
        try:
            if progress_callback:
                progress_callback(f"🔍 Analizando: {url}")

            # Si es una URL específica y no está en la lista, saltarla
            if self.specific_urls and url not in self.specific_urls:
                if progress_callback:
                    progress_callback(f"⚠️ URL fuera de la lista específica: {url}")
                return

            # Headers personalizados para mejor compatibilidad
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'es-ES,es;q=0.8,en-US;q=0.5,en;q=0.3',
                'Cache-Control': 'no-cache',
                'Pragma': 'no-cache'
            }

            # Inicializar variables de contenido
            content = None
            initial_content = ""
            status_code = None
            use_playwright = False
            source_method = None  # para logging: 'requests' o 'playwright'

            # Intentar primero con requests
            try:
                try:
                    # Primer intento: tiempo de conexión y lectura separados para evitar bloqueos largos
                    response = self.session.get(
                        url,
                        timeout=(10, 30),  # (connect timeout, read timeout)
                        headers=headers,
                        allow_redirects=True,
                        verify=False,
                    )

                    content_type = response.headers.get('content-type', '')
                    content_length = response.headers.get('content-length')
                    status_code = response.status_code

                    # Si el contenido parece ser HTML, leerlo completamente
                    if content_type and 'html' in content_type.lower():
                        initial_content = response.text or ""
                    else:
                        initial_content = ""
                        response.close()

                except (requests.exceptions.ReadTimeout, requests.exceptions.ConnectTimeout):
                    # Segundo intento con mayor read timeout
                    response = self.session.get(
                        url,
                        timeout=(10, 60),
                        headers=headers,
                        allow_redirects=True,
                        verify=False,
                    )

                    content_type = response.headers.get('content-type', '')
                    content_length = response.headers.get('content-length')
                    initial_content = response.text or ""
                    status_code = response.status_code

                # MEJORADO: Detección inteligente de cuándo usar Playwright
                try:
                    # Reutilizar un handler de Playwright por instancia del analyzer para
                    # evitar abrir/cerrar múltiples navegadores continuamente.
                    if not self.playwright_handler:
                        self.playwright_handler = PlaywrightHandler(headless=self.headless_mode)
                        try:
                            self.playwright_handler.initialize()
                        except Exception:
                            pass

                    pw = self.playwright_handler
                    
                    # NUEVA LÓGICA: Decidir usar Playwright basado en:
                    # 1. Cloudflare challenge
                    # 2. HTML skeleton (SPA)
                    # 3. Extracción fallida con BeautifulSoup
                    
                    # Check 1: Cloudflare protegido
                    if is_cloudflare_challenge(initial_content, status_code):
                        logger.info(f"🔒 Cloudflare detectado en {url} → Usando Playwright")
                        use_playwright = True
                    
                    # Check 2: HTML skeleton (SPA)
                    elif is_skeleton_html(initial_content):
                        logger.info(f"🎭 HTML skeleton detectado en {url} → Usando Playwright")
                        use_playwright = True
                    
                    # Check 3: Validar extracción de BeautifulSoup
                    else:
                        try:
                            soup = BeautifulSoup(initial_content, 'html.parser')
                            if not validate_extraction(soup):
                                logger.info(f"⚠️  Extracción débil en {url} → Usando Playwright")
                                use_playwright = True
                            else:
                                # Extracción exitosa, usar el contenido de requests
                                use_playwright = False
                        except Exception:
                            # Si BeautifulSoup falla, mejor usar Playwright
                            use_playwright = True
                    
                except Exception as e:
                    logger.debug(f"Error en decisión de Playwright: {e}")
                    # Por seguridad, si hay error en la lógica, ser conservador
                    use_playwright = len(initial_content.strip()) < 300

            except Exception as e:
                logger.warning(f"Request inicial falló para {url}, intentaremos Playwright: {e}")
                use_playwright = True

            # Si es necesario, usar Playwright
            # Circuit breaker: si el dominio tiene el circuito abierto, evitamos Playwright
            domain = urlparse(url).netloc.replace('www.', '')
            if self._is_circuit_open(domain):
                logger.warning(f"Circuit open for domain {domain}, evitando Playwright para {url}")
                use_playwright = False

            if use_playwright:
                if progress_callback:
                    progress_callback(f"🎭 Usando Playwright para: {url}")
                try:
                    # Asegurarse de tener un handler inicializado
                    if not self.playwright_handler:
                        self.playwright_handler = PlaywrightHandler(headless=self.headless_mode)
                        try:
                            self.playwright_handler.initialize()
                        except Exception:
                            pass

                    pw_content, pw_status = self.playwright_handler.get_page_content(
                        url,
                        wait_for_selectors=[
                            'h1', 'title',
                            'meta[name="description"]'
                        ],
                        post_load_wait=0  # OPTIMIZADO: reducido de 5 a 0 (no necesario)
                    )
                    # Normalizar salida del Playwright
                    if pw_content:
                        content = pw_content
                        status_code = pw_status
                        source_method = 'playwright'
                    else:
                        content = initial_content or None
                        source_method = 'requests' if initial_content else 'none'
                except Exception as e:
                    logger.error(f"Error con Playwright en {url}: {e}")
                    content = initial_content or None
                    source_method = 'requests' if initial_content else 'none'
            else:
                content = initial_content
                source_method = 'requests' if initial_content else 'none'

            # Preparar page_data base
            page_data = {
                'URL': url,
                'Status Code': status_code,
                'H1': None,
                'Meta Titulo': None,
                'Meta Description': None,
                'Longitud Meta Titulo': 0,
                'Longitud Meta Description': 0,
                'H2': None,
                'Palabras Clave': None,
                'Canonical': None,
                'Robots': None,
                'Anchor': None,
                'Word Count': 0,
                'longitud_url': len(url),
                'Cantidad H1': 0,
                'hreflang_es': None,
                'hreflang_en': None,
                'hreflang_pt': None
            }

            # Si no tenemos contenido, registrar y salir (pero dejar entry mínima)
            if not content or not str(content).strip():
                logger.warning(f"Contenido vacío para {url} (método: {source_method})")
                # Añadir entrada mínima y salir
                self.results.append(page_data)
                return

            # Asegurar content como str y decodificar si es bytes
            if isinstance(content, bytes):
                try:
                    content = content.decode('utf-8', errors='replace')
                except Exception:
                    content = content.decode('latin-1', errors='replace')

            # Ahora parsear con BeautifulSoup (sin pasar from_encoding para evitar warning)
            soup = BeautifulSoup(content, 'html.parser')

            # Limpiar scripts, estilos, iframes
            for script in soup(['script', 'style', 'iframe']):
                try:
                    script.decompose()
                except Exception:
                    pass

            # Extraer Meta Título
            title_tag = soup.find('title')
            if title_tag:
                title_text = title_tag.get_text().strip()
                page_data['Meta Titulo'] = title_text
                page_data['Longitud Meta Titulo'] = len(title_text)
                if title_text:
                    self.meta_titles.setdefault(title_text, []).append(url)

            # Meta description
            meta_desc = soup.find('meta', attrs={'name': 'description'})
            if meta_desc:
                desc_text = meta_desc.get('content', '').strip()
                page_data['Meta Description'] = desc_text
                page_data['Longitud Meta Description'] = len(desc_text)
                if desc_text:
                    self.meta_desc.setdefault(desc_text, []).append(url)

            # H1s
            h1_tags = soup.find_all('h1')
            if not h1_tags:
                # fallback selectors
                candidates = ['title', 'page-title', 'heading', 'hero-title', 'site-title', 'titulo', 'titulo-pagina']
                for cand in candidates:
                    try:
                        found = soup.find(attrs={'class': lambda v, c=cand: v and c in v.lower()})
                        if found:
                            h1_tags.append(found)
                    except Exception:
                        continue
                if not h1_tags:
                    h1_role = soup.find(attrs={'role': 'heading'})
                    if h1_role:
                        h1_tags.append(h1_role)

            h1_texts = [h.get_text().strip() for h in h1_tags if h.get_text().strip()]
            if h1_texts:
                page_data['H1'] = ' | '.join(h1_texts)
                page_data['Cantidad H1'] = len(h1_texts)
                for h1_text in h1_texts:
                    self.h1s.setdefault(h1_text, []).append(url)

            # H2s
            h2_tags = soup.find_all('h2')
            if h2_tags:
                page_data['H2'] = ' | '.join(h.get_text().strip() for h in h2_tags if h.get_text().strip())

            # Canonical
            canonical = soup.find('link', rel='canonical')
            if canonical:
                page_data['Canonical'] = canonical.get('href', '')

            # Robots
            robots = soup.find('meta', attrs={'name': 'robots'})
            if robots:
                page_data['Robots'] = robots.get('content', '')

            # Hreflangs (verificar estado Y AGREGAR A COLA)
            hreflangs = soup.find_all('link', rel='alternate', hreflang=True)
            for hreflang in hreflangs:
                lang = hreflang.get('hreflang', '').lower()
                href = hreflang.get('href', '')
                if not href:
                    continue
                full_href = urljoin(url, href)
                
                # ✅ NUEVO: Agregar hreflang a la cola para que sea descubierto
                self.add_url_to_queue(full_href)
                
                link_status = self._check_link_status(full_href)
                code = link_status.get('code', '') if isinstance(link_status, dict) else ''
                status_text = f"{full_href} ({code if code else 'Error'})"
                if lang.startswith('es'):
                    page_data['hreflang_es'] = status_text
                elif lang.startswith('en'):
                    page_data['hreflang_en'] = status_text
                elif lang.startswith('pt'):
                    page_data['hreflang_pt'] = status_text

            # Word count (usar contenedor principal si existe)
            def _find_main_container(soup_obj):
                main = soup_obj.find('main')
                if main:
                    return main
                candidates = ['content', 'main', 'page', 'site', 'wrap', 'container', 'app', 'region', 'contenido']
                for attr in ['id', 'class']:
                    for cand in candidates:
                        try:
                            found = soup_obj.find(attrs={attr: lambda v, c=cand: v and c in v.lower()})
                            if found:
                                return found
                        except Exception:
                            continue
                return soup_obj.find('body') or soup_obj

            main_container = _find_main_container(soup)
            try:
                text_container = main_container
                text_content = ' '.join([
                    tag.get_text().strip()
                    for tag in text_container.find_all(['p', 'span', 'div', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li'])
                    if tag.get_text().strip()
                ])
            except Exception:
                text_content = ' '.join([
                    tag.get_text().strip()
                    for tag in soup.find_all(['p', 'span', 'div', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li'])
                    if tag.get_text().strip()
                ])
            page_data['Word Count'] = len(text_content.split())

            # Palabras clave (top 10)
            import re
            from collections import Counter
            stopwords = {'de', 'la', 'que', 'el', 'en', 'y', 'a', 'los', 'del', 'las', 'un', 'por', 'con', 'una',
                         'su', 'para', 'es', 'al', 'lo', 'como', 'más', 'o', 'pero', 'sus', 'le', 'ha', 'me', 'si',
                         'sin', 'sobre', 'este', 'ya', 'entre', 'cuando', 'todo', 'esta', 'ser', 'son', 'dos', 'también',
                         'fue', 'había', 'era', 'muy', 'años', 'hasta', 'desde', 'está', 'mi', 'porque', 'qué', 'sólo',
                         'han', 'yo', 'hay', 'vez', 'puede', 'todos', 'así', 'nos', 'ni', 'parte', 'tiene', 'él',
                         'the', 'and', 'to', 'of', 'in', 'for', 'is', 'on', 'that', 'by', 'this', 'with', 'i', 'you',
                         'it', 'not', 'or', 'be', 'are', 'from', 'at', 'as', 'your', 'all', 'have', 'new', 'more',
                         'an', 'was', 'we', 'will', 'can', 'us', 'about', 'if', 'my', 'has', 'but', 'our', 'one',
                         'other', 'do', 'no', 'they', 'he', 'may', 'what', 'which', 'their', 'any', 'there', 'who'}
            words = re.findall(r'\b\w+\b', text_content.lower())
            content_words = [word for word in words if word not in stopwords and len(word) > 3]
            word_freq = Counter(content_words).most_common(10)
            page_data['Palabras Clave'] = ', '.join(word for word, _ in word_freq)

            # Procesar enlaces si está habilitado (y si no es modo specific_urls)
            anchors = []
            links_found = 0
            if self.analyze_links and not self.specific_urls:
                source_domain = urlparse(url).netloc.replace('www.', '')
                # Recolectar enlaces y procesar sus estados en paralelo para mejorar rendimiento
                link_entries = []
                for element in soup.find_all(['a', 'area', 'link']):
                    href = element.get('href', '').strip()
                    if not href or href.startswith(('javascript:', 'data:', 'tel:', 'mailto:')):
                        continue
                    try:
                        full_url = urljoin(url, href)
                        parsed_url = urlparse(full_url)
                        if not parsed_url.scheme or not parsed_url.netloc:
                            continue
                        target_domain = parsed_url.netloc.replace('www.', '')
                        anchor_text = element.get_text().strip()
                        link_type = 'Interno' if source_domain == target_domain else 'Externo'
                        link_entries.append({
                            'element': element,
                            'full_url': full_url,
                            'anchor_text': anchor_text,
                            'link_type': link_type,
                            'target_domain': target_domain,
                            'hreflang': element.get('hreflang')
                        })
                    except Exception as e:
                        if progress_callback:
                            progress_callback(f"⚠️ Error procesando enlace en {url}: {str(e)}")

                # Verificar el estado de los enlaces en paralelo (con límite razonable de workers)
                if link_entries:
                    try:
                        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
                            futures = {executor.submit(self._check_link_status, entry['full_url']): entry for entry in link_entries}
                            for fut in concurrent.futures.as_completed(futures):
                                entry = futures[fut]
                                try:
                                    link_status = fut.result()
                                except Exception as e:
                                    link_status = {'status': f'Error: {e}', 'code': 'ERROR'}

                                link_data = {
                                    'Source Page': url,
                                    'Source Domain': source_domain,
                                    'Target URL': entry['full_url'],
                                    'Target Domain': entry['target_domain'],
                                    'Domain Authority': '',
                                    'Link Type': entry['link_type'],
                                    'Anchor Text': entry['anchor_text'] if entry['anchor_text'] else '',
                                    'Status': link_status.get('status', ''),
                                    'Status Code': link_status.get('code', '')
                                }
                                self.links.append(link_data)
                                links_found += 1
                                if entry['anchor_text']:
                                    anchors.append(entry['anchor_text'])
                                # Si es interno y válido, añadir a la cola usando add_url_to_queue
                                if entry['link_type'] == 'Interno' and self.is_valid_url(entry['full_url']):
                                    self.add_url_to_queue(entry['full_url'])
                                # Si el enlace tiene hreflang y apunta a una URL válida, añadir
                                if entry.get('hreflang'):
                                    hreflang_url = entry['full_url']
                                    if self.is_valid_url(hreflang_url):
                                        self.add_url_to_queue(hreflang_url)
                    except Exception as e:
                        # Fallback: procesar secuencialmente si el executor falla
                        if progress_callback:
                            progress_callback(f"⚠️ Error en verificación paralela de enlaces: {e}")
                        for entry in link_entries:
                            link_status = self._check_link_status(entry['full_url'])
                            link_data = {
                                'Source Page': url,
                                'Source Domain': source_domain,
                                'Target URL': entry['full_url'],
                                'Target Domain': entry['target_domain'],
                                'Domain Authority': '',
                                'Link Type': entry['link_type'],
                                'Anchor Text': entry['anchor_text'] if entry['anchor_text'] else '',
                                'Status': link_status.get('status', ''),
                                'Status Code': link_status.get('code', '')
                            }
                            self.links.append(link_data)
                            links_found += 1
                            if entry['anchor_text']:
                                anchors.append(entry['anchor_text'])
                            if entry['link_type'] == 'Interno' and self.is_valid_url(entry['full_url']):
                                self.add_url_to_queue(entry['full_url'])

            if anchors:
                page_data['Anchor'] = ' | '.join(set(anchors))

            # Analizar imágenes si está habilitado
            if self.analyze_images:
                favicon = soup.find('link', rel='icon') or soup.find('link', rel='shortcut icon')
                if favicon and favicon.get('href'):
                    favicon_url = urljoin(url, favicon.get('href'))
                    favicon_data = {
                        'Pagina Origen': url,
                        'URL Imagen': favicon_url,
                        'Title': 'Favicon',
                        'Alt': 'Favicon',
                        'Tipo Imagen': os.path.splitext(favicon_url)[1][1:].upper() or 'ICO',
                        'Peso': '0 KB',
                        'Estado': 'Pendiente verificar'
                    }
                    self.images.append(favicon_data)
                img_tags = soup.find_all('img')
                for source in soup.find_all(['source', 'picture']):
                    if source.get('srcset'):
                        for src in source['srcset'].split(','):
                            src = src.strip().split()[0]
                            img = soup.new_tag('img')
                            img['src'] = src
                            img_tags.append(img)
                # Analizar imágenes en paralelo para mejorar rendimiento
                if img_tags:
                    try:
                        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as img_executor:
                            img_futures = [img_executor.submit(self._analyze_image, img, url) for img in img_tags]
                            for fut in concurrent.futures.as_completed(img_futures):
                                try:
                                    img_data = fut.result()
                                except Exception:
                                    img_data = None
                                if img_data:
                                    self.images.append(img_data)
                    except Exception:
                        # Fallback secuencial si hay problema con el executor
                        for img in img_tags:
                            img_data = self._analyze_image(img, url)
                            if img_data:
                                self.images.append(img_data)

            # Añadir page_data a resultados
            self.results.append(page_data)

            # Logging informativo: método que dio contenido y enlaces encontrados
            logger.info(f"crawl_page: {url} -> fuente: {source_method}, enlaces extraídos: {links_found}")

            # Esperar delay fragmentado (interrumpible)
            delay_total = max(0, float(self.delay))
            slept = 0.0
            step = 0.1
            while slept < delay_total and self.is_running:
                if self.is_paused:
                    break
                time.sleep(step)
                slept += step

        except Exception as e:
            if progress_callback:
                progress_callback(f"⚠️ Error analizando {url}: {str(e)}")
            logger.exception(f"Excepción en crawl_page para {url}: {e}")
            # Intentar recuperar algo de información incluso si hay error
            try:
                page_data = {
                    'URL': url,
                    'Status Code': status_code if status_code else 'Error',
                    'H1': None,
                    'Meta Titulo': None,
                    'Meta Description': None,
                    'Longitud Meta Titulo': 0,
                    'Longitud Meta Description': 0,
                    'H2': None,
                    'Palabras Clave': None,
                    'Canonical': None,
                    'Robots': None,
                    'Anchor': None,
                    'Word Count': 0,
                    'longitud_url': len(url),
                    'Cantidad H1': 0,
                    'hreflang_es': None,
                    'hreflang_en': None,
                    'hreflang_pt': None
                }
                if 'content' in locals() and content:
                    try:
                        soup = BeautifulSoup(content, 'html.parser')
                        title_tag = soup.find('title')
                        if title_tag:
                            page_data['Meta Titulo'] = title_tag.get_text().strip()
                            page_data['Longitud Meta Titulo'] = len(page_data['Meta Titulo'])
                        meta_desc = soup.find('meta', attrs={'name': 'description'})
                        if meta_desc:
                            desc_text = meta_desc.get('content', '').strip()
                            page_data['Meta Description'] = desc_text
                            page_data['Longitud Meta Description'] = len(desc_text)
                        h1_tags = soup.find_all('h1')
                        if h1_tags:
                            page_data['H1'] = ' | '.join(h.get_text().strip() for h in h1_tags if h.get_text().strip())
                            page_data['Cantidad H1'] = len(h1_tags)
                    except Exception:
                        pass
                self.results.append(page_data)
            except Exception:
                self.results.append({
                    'URL': url,
                    'Status Code': 'Error',
                    'H1': None,
                    'Meta Titulo': None,
                    'Meta Description': None
                })
            
    def stop_crawling(self):
        """Detiene el proceso de crawling y guarda el estado."""
        self.is_running = False
        self.is_paused = True
        
        # Guardar el estado actual
        self.current_state = {
            'visited': self.visited.copy(),
            'to_visit': list(self.to_visit),
            'results': self.results.copy(),
            'images': self.images.copy() if hasattr(self, 'images') else [],
            'links': self.links.copy() if hasattr(self, 'links') else [],
            'specific_urls': self.specific_urls.copy() if self.specific_urls else None,
            'analyze_images': self.analyze_images,
            'analyze_links': self.analyze_links,
        }
        
    def resume_crawling(self):
        """Reanuda el proceso de crawling desde el último estado guardado."""
        if not self.is_paused:
            return False
            
        try:
            # Restaurar estado
            self.visited = self.current_state['visited']
            self.to_visit = deque(self.current_state['to_visit'])
            self.results = self.current_state['results']
            self.images = self.current_state['images']
            self.links = self.current_state['links']
            self.specific_urls = self.current_state['specific_urls']
            self.analyze_images = self.current_state['analyze_images']
            self.analyze_links = self.current_state['analyze_links']
            
            # Restablecer flags
            self.is_running = True
            self.is_paused = False
            return True
            
        except Exception:
            return False
        
    def crawl_site(self, progress_callback=None, completion_callback=None):
        """Ejecuta el análisis completo del sitio."""
        self.start_time = time.time()
        # Definir total como infinito cuando max_pages == 1 (modo sin límite)
        total = float('inf') if self.max_pages == 1 else self.max_pages
        
        if progress_callback:
            progress_callback(f"🚀 Iniciando análisis de: {self.base_url}", {'completed': len(self.visited), 'total': total})
            progress_callback(f"⏰ Delay entre requests: {self.delay}s", {'completed': len(self.visited), 'total': total})
        
        while self.to_visit and self.is_running:
            # Si está pausado, esperar hasta que se reanude o se detenga
            while self.is_paused and self.is_running:
                time.sleep(0.3)

            # Verificar si max_pages limita (si max_pages != 1)
            if self.max_pages != 1 and len(self.visited) >= self.max_pages:
                if progress_callback:
                    progress_callback(f"🎯 Alcanzado límite de {self.max_pages} páginas", {'completed': len(self.visited), 'total': total})
                break
                
            url = self.to_visit.popleft()
            # Normalizar URL antes de procesar
            url = self._normalize_url(url)
            if url not in self.visited:
                self.visited.add(url)

                # Registrar longitud de resultados antes de procesar para detectar si crawl_page añadió algo
                before_results_len = len(self.results)

                self.crawl_page(url, progress_callback)

                # Si crawl_page no añadió un resultado para esta URL (por cualquier razón), añadimos uno mínimo
                found = any(r.get('URL') == url for r in self.results)
                if not found:
                    logger.warning(f"crawl_page no registró resultado para {url} — añadiendo registro mínimo.")
                    self.results.append({
                        'URL': url,
                        'Status Code': 'No Content',
                        'H1': None,
                        'Meta Titulo': None,
                        'Meta Description': None
                    })

                if progress_callback:
                    # Calcular progreso y tiempos
                    elapsed_time = time.time() - self.start_time
                    pages_analyzed = len(self.visited)
                    
                    # Formatear tiempo transcurrido
                    hours = int(elapsed_time // 3600)
                    minutes = int((elapsed_time % 3600) // 60)
                    seconds = int(elapsed_time % 60)
                    time_str = f"{hours}h {minutes}m {seconds}s"
                    
                    # Calcular tiempo estimado restante
                    remaining_str = "N/A"
                    if pages_analyzed > 0 and self.max_pages != 1:
                        # Velocidad promedio: segundos por página
                        avg_time_per_page = elapsed_time / pages_analyzed
                        pages_remaining = self.max_pages - pages_analyzed
                        estimated_remaining = avg_time_per_page * pages_remaining
                        
                        if estimated_remaining > 0:
                            rem_hours = int(estimated_remaining // 3600)
                            rem_minutes = int((estimated_remaining % 3600) // 60)
                            rem_seconds = int(estimated_remaining % 60)
                            remaining_str = f"{rem_hours}h {rem_minutes}m {rem_seconds}s"
                    elif self.max_pages == 1:
                        remaining_str = "Indefinido (sin límite)"
                    
                    # Status con detalles completos
                    status = f"📊 Progreso del análisis:\n"
                    status += f"   - Páginas analizadas: {pages_analyzed}\n"
                    status += f"   - Tiempo transcurrido: {time_str}\n"
                    status += f"   - Tiempo estimado restante: {remaining_str}\n"
                    status += f"   - URLs pendientes: {len(self.to_visit)}"
                    
                    progress_callback(status, {'completed': pages_analyzed, 'total': total, 'pending': len(self.to_visit)})
                
                # Delay respetando pausa/detención (fragmentado para ser interrumpible)
                delay_total = max(0, float(self.delay))
                slept = 0.0
                step = 0.1
                while slept < delay_total and self.is_running:
                    if self.is_paused:
                        break
                    time.sleep(step)
                    slept += step
        
        # Mensaje final
        if progress_callback:
            elapsed_time = time.time() - self.start_time
            hours = int(elapsed_time // 3600)
            minutes = int((elapsed_time % 3600) // 60)
            seconds = int(elapsed_time % 60)
            time_str = f"{hours}h {minutes}m {seconds}s"
            
            final_status = "="*50 + "\n"
            final_status += "🎉 Análisis completado\n"
            final_status += f"📈 Resumen final:\n"
            final_status += f"   - Total páginas analizadas: {len(self.visited)}\n"
            final_status += f"   - Tiempo total: {time_str}\n"
            final_status += f"   - Páginas con error: {len([r for r in self.results if r.get('Status Code') == 'Error'])}"
            
            progress_callback(final_status, {'completed': len(self.visited), 'total': total, 'pending': len(self.to_visit)})
            
        if completion_callback:
            completion_callback()
        # Cerrar handler de Playwright si existe (liberar recursos)
        try:
            if self.playwright_handler:
                try:
                    self.playwright_handler.close()
                except Exception:
                    pass
                self.playwright_handler = None
        except Exception:
            pass
            
    def generate_report(self, progress_callback=None):
        """Genera un reporte Excel con los resultados del análisis."""
        if not self.results:
            if progress_callback:
                progress_callback("❌ No hay datos para generar el reporte")
            return None
            
        if progress_callback:
            progress_callback("📊 Generando reporte en Excel...")
            
        try:
            # Generar nombre del archivo basado en el modo (completo o URLs específicas)
            # Formato ejemplo: 'Analisis Seo Completo 30,10,2025,1430.xlsx' o
            # 'Analisis URLs Especificas 30,10,2025,1430.xlsx'
            ts = datetime.now().strftime("%d,%m,%Y,%H%M")
            if self.specific_urls:
                default_filename = f"Analisis URLs Especificas {ts}.xlsx"
            else:
                default_filename = f"Analisis Seo Completo {ts}.xlsx"
            
            # Permitir al usuario elegir dónde guardar
            filename = filedialog.asksaveasfilename(
                defaultextension=".xlsx",
                filetypes=[("Excel files", "*.xlsx"), ("All files", "*.*")],
                initialfile=default_filename
            )
            
            if not filename:
                return None
            
            with pd.ExcelWriter(filename, engine='openpyxl') as writer:
                # Calcular métricas para el resumen
                total_pages = len(self.results)
                successful_pages = len([r for r in self.results if r.get('Status Code') == 200])
                error_pages = total_pages - successful_pages
                
                # Calcular tiempo total
                total_time = time.time() - self.start_time if self.start_time else 0
                hours = int(total_time // 3600)
                minutes = int((total_time % 3600) // 60)
                seconds = int(total_time % 60)
                time_str = f"{hours}h {minutes}m {seconds}s"
                
                # Crear DataFrame de resumen
                summary_data = {
                    'Métrica': [
                        'Total Páginas Analizadas',
                        'Páginas Exitosas',
                        'Páginas con Error',
                        'Tiempo Total Análisis',
                        'Tipo Análisis',
                        'Dominio Analizado'
                    ],
                    'Valor': [
                        total_pages,
                        successful_pages,
                        error_pages,
                        time_str,
                        'Análisis Completo' if not self.specific_urls else 'Análisis URLs Específicas',
                        self.base_url
                    ]
                }
                
                # Guardar hoja de resumen
                pd.DataFrame(summary_data).to_excel(writer, sheet_name='Resumen SEO', index=False)

                # No crear hojas adicionales, toda la información irá en la hoja de detalles
                
                # Organizar columnas para la hoja de detalles
                detail_columns = [
                    'URL',
                    'Status Code',
                    'H1',
                    'Meta Titulo',
                    'Meta Description',
                    'Longitud Meta Titulo',
                    'Longitud Meta Description',
                    'H2',
                    'Palabras Clave',
                    'Canonical',
                    'Robots',
                    'Anchor',
                    'Word Count',
                    'longitud_url',
                    'Cantidad H1',
                    'hreflang_es',
                    'hreflang_en',
                    'hreflang_pt'
                ]
                
                # Crear DataFrame y ordenar columnas
                details_df = pd.DataFrame(self.results)
                # Asegurar que todas las columnas existan
                for col in detail_columns:
                    if col not in details_df.columns:
                        details_df[col] = ''
                # Ordenar columnas y guardar
                details_df = details_df[detail_columns]
                details_df.to_excel(writer, sheet_name='Detalles por Página', index=False)
                
                # Generar hoja de problemas SEO
                seo_issues = []
                
                # 1. Detectar Meta Títulos duplicados
                for title, urls in self.meta_titles.items():
                    if len(urls) > 1:
                        for url in urls:
                            seo_issues.append({
                                'URL': url,
                                'Tipo de Problema': 'Meta Título duplicado',
                                'Descripción': f'Meta Título "{title[:50]}..." usado en {len(urls)} páginas',
                                'Gravedad': 'Alta'
                            })
                
                # 2. Detectar H1s duplicados
                for h1, urls in self.h1s.items():
                    if len(urls) > 1:
                        for url in urls:
                            seo_issues.append({
                                'URL': url,
                                'Tipo de Problema': 'H1 duplicado',
                                'Descripción': f'H1 "{h1[:50]}..." usado en {len(urls)} páginas',
                                'Gravedad': 'Alta'
                            })
                
                # 3. Analizar problemas página por página
                for result in self.results:
                    url = result.get('URL', '')
                    
                    # Páginas sin H1
                    if not result.get('H1') or result.get('H1') == 'No tiene H1':
                        seo_issues.append({
                            'URL': url,
                            'Tipo de Problema': 'Sin H1',
                            'Descripción': 'La página no tiene encabezado H1',
                            'Gravedad': 'Alta'
                        })
                    
                    # Múltiples H1s
                    if result.get('Cantidad H1', 0) > 1:
                        seo_issues.append({
                            'URL': url,
                            'Tipo de Problema': 'Múltiples H1',
                            'Descripción': f'La página tiene {result.get("Cantidad H1")} encabezados H1',
                            'Gravedad': 'Media'
                        })
                    
                    # Sin Meta Título
                    if not result.get('Meta Titulo'):
                        seo_issues.append({
                            'URL': url,
                            'Tipo de Problema': 'Sin Meta Título',
                            'Descripción': 'La página no tiene meta título',
                            'Gravedad': 'Alta'
                        })
                    
                    # Meta Título muy largo
                    elif result.get('Longitud Meta Titulo', 0) > 60:
                        seo_issues.append({
                            'URL': url,
                            'Tipo de Problema': 'Meta Título muy largo',
                            'Descripción': f'Meta Título tiene {result.get("Longitud Meta Titulo")} caracteres (máx. recomendado: 60)',
                            'Gravedad': 'Media'
                        })
                    
                    # Sin Meta Description
                    if not result.get('Meta Description'):
                        seo_issues.append({
                            'URL': url,
                            'Tipo de Problema': 'Sin Meta Description',
                            'Descripción': 'La página no tiene meta description',
                            'Gravedad': 'Alta'
                        })
                    
                    # Meta Description muy larga o muy corta
                    else:
                        desc_len = result.get('Longitud Meta Description', 0)
                        if desc_len > 160:
                            seo_issues.append({
                                'URL': url,
                                'Tipo de Problema': 'Meta Description muy larga',
                                'Descripción': f'Meta Description tiene {desc_len} caracteres (máx. recomendado: 160)',
                                'Gravedad': 'Media'
                            })
                        elif desc_len < 50:
                            seo_issues.append({
                                'URL': url,
                                'Tipo de Problema': 'Meta Description muy corta',
                                'Descripción': f'Meta Description tiene solo {desc_len} caracteres (mín. recomendado: 50)',
                                'Gravedad': 'Baja'
                            })
                    
                    # URL muy larga
                    if len(url) > 115:
                        seo_issues.append({
                            'URL': url,
                            'Tipo de Problema': 'URL muy larga',
                            'Descripción': f'URL tiene {len(url)} caracteres (máx. recomendado: 115)',
                            'Gravedad': 'Baja'
                        })
                
                # Guardar problemas SEO en el Excel
                if seo_issues:
                    issues_df = pd.DataFrame(seo_issues)
                    # Ordenar por gravedad (Alta > Media > Baja)
                    gravity_order = {'Alta': 0, 'Media': 1, 'Baja': 2}
                    issues_df['Gravedad_orden'] = issues_df['Gravedad'].map(gravity_order)
                    issues_df = issues_df.sort_values('Gravedad_orden')
                    issues_df = issues_df.drop('Gravedad_orden', axis=1)
                    issues_df.to_excel(writer, sheet_name='Problemas SEO', index=False)
                    
                # Generar hoja de imágenes
                if self.images:
                    images_df = pd.DataFrame(self.images)
                    # Ordenar columnas
                    image_columns = [
                        'Pagina Origen',
                        'URL Imagen',
                        'Title',
                        'Alt',
                        'Tipo Imagen',
                        'Peso',
                        'Estado'
                    ]
                    # Asegurar que todas las columnas existan
                    for col in image_columns:
                        if col not in images_df.columns:
                            images_df[col] = ''
                    # Ordenar columnas y guardar
                    images_df = images_df[image_columns]
                    images_df.to_excel(writer, sheet_name='Imágenes', index=False)
                
                # Generar hoja de Enlaces Detallados
                if self.links:
                    links_df = pd.DataFrame(self.links)
                    # Definir y ordenar columnas
                    link_columns = [
                        'Source Page',
                        'Source Domain',
                        'Target URL',
                        'Target Domain',
                        'Domain Authority',
                        'Link Type',
                        'Anchor Text'
                    ]
                    # Asegurar que todas las columnas existan
                    for col in link_columns:
                        if col not in links_df.columns:
                            links_df[col] = ''
                    # Ordenar columnas y guardar
                    links_df = links_df[link_columns]
                    links_df.to_excel(writer, sheet_name='Enlaces Detallados', index=False)
                
            if progress_callback:
                progress_callback(f"💾 Reporte guardado como: {filename}")
                
            return filename
            
        except Exception as e:
            if progress_callback:
                progress_callback(f"❌ Error al guardar el reporte: {str(e)}")
            return None
