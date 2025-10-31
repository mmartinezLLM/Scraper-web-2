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

# Suprimir advertencias de SSL cuando intentionalmente usamos verify=False
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SEOAnalyzer:
    """Analizador SEO para sitios web."""
    
    def __init__(self, base_url, max_pages=10, delay=1, specific_urls=None, analyze_images=True, analyze_links=True, headless_mode=False):
        """
        Inicializa el analizador SEO.
        
        Args:
            base_url (str): URL base para comenzar el análisis
            max_pages (int): Número máximo de páginas a analizar (1 = sin límite)
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
        """Valida si una URL debe ser analizada."""
        try:
            parsed = urlparse(url)
            if not parsed.netloc:
                return False
                
            # En modo de URLs específicas permitimos analizar URLs de otros dominios
            if not self.specific_urls:
                if not self.is_same_domain(url, self.base_url):
                    return False
                
            # Verificar extensiones y protocolos no válidos
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
            invalid_protocols = ['mailto:', 'tel:', 'javascript:', 'data:']
            
            # Verificar patrones de URLs de recursos estáticos
            static_patterns = [
                '/_next/static/',
                '/static/',
                '/assets/',
                '/dist/',
                '/build/',
                '/themes/'
            ]
            
            # Verificar extensiones excluidas
            if any(url.lower().endswith(ext) for ext in excluded_extensions):
                # Si es una imagen, agregarla a la lista de imágenes pero no analizarla como página
                if any(url.lower().endswith(img_ext) for img_ext in ['.jpg', '.jpeg', '.png', '.gif', '.ico', '.svg', '.webp']):
                    if self.analyze_images:
                        img_data = {
                            'Pagina Origen': url,  # En este caso la imagen es la misma URL
                            'URL Imagen': url,
                            'Title': '',
                            'Alt': '',
                            'Tipo Imagen': url.split('.')[-1].upper(),
                            'Peso': '0 KB',  # No verificamos el peso para evitar requests adicionales
                            'Estado': 'No verificado'
                        }
                        self.images.append(img_data)
                return False
                
            # Verificar protocolos no válidos
            if any(url.lower().startswith(proto) for proto in invalid_protocols):
                return False
                
            # Verificar patrones de recursos estáticos
            if any(pattern in url.lower() for pattern in static_patterns):
                return False
            
            return True
        except Exception:
            return False
            
    def add_url_to_queue(self, url):
        """Añade una URL a la cola si cumple los criterios.

        Se realiza una verificación ligera (HEAD, y si falla GET) para
        confirmar que la URL existe antes de agregarla, lo que mejora
        la fiabilidad del crawling.
        """
        try:
            url = self._normalize_url(url)
            # Rechazar si ya fue visitada o ya está en cola
            if url in self.visited or url in self.to_visit:
                return False

            # Validar URL básica (si falla, no la añadimos)
            if not self.is_valid_url(url):
                return False

            # En modo específico solo añadimos si la URL está en la lista explícita
            if self.specific_urls is not None and url not in self.specific_urls:
                return False

            # Intentar HEAD para confirmar existencia
            try:
                resp = self.session.head(url, timeout=8, allow_redirects=True, verify=False)
                code = getattr(resp, 'status_code', None)
                if code and code < 400:
                    self.to_visit.append(url)
                    return True
                # Si HEAD devuelve 405 o >=400, intentar GET ligero
                if code == 405 or (code and code >= 400):
                    resp2 = self.session.get(url, timeout=10, stream=True, allow_redirects=True, verify=False)
                    if getattr(resp2, 'status_code', 500) < 400:
                        self.to_visit.append(url)
                        return True
                    return False
            except Exception:
                # Si falla la verificación remota, no agregar para evitar recorrer URLs inexistentes
                return False

        except Exception:
            return False

        return False
    def _check_link_status(self, url):
        """Verifica el estado de un enlace y retorna su información."""
        try:
            # Request HEAD primero (más rápido)
            response = self.session.head(url, 
                                      timeout=10, 
                                      allow_redirects=True,
                                      verify=False)
            
            # Si es 405 (Method Not Allowed), intentar con GET
            if response.status_code == 405:
                response = self.session.get(url, 
                                         timeout=10,
                                         allow_redirects=True,
                                         verify=False)
            
            if response.status_code == 200:
                return {'status': 'OK', 'code': 200}
            elif 300 <= response.status_code < 400:
                return {'status': 'Redirigido', 'code': response.status_code}
            elif response.status_code == 404:
                return {'status': 'No encontrado', 'code': 404}
            else:
                return {'status': f'Error ({response.status_code})', 'code': response.status_code}
                
        except requests.exceptions.SSLError:
            return {'status': 'Error SSL', 'code': 'SSL_ERROR'}
        except requests.exceptions.ConnectionError:
            return {'status': 'Error de conexión', 'code': 'CONN_ERROR'}
        except requests.exceptions.Timeout:
            return {'status': 'Timeout', 'code': 'TIMEOUT'}
        except Exception as e:
            return {'status': f'Error: {str(e)}', 'code': 'ERROR'}
            
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
                return
                
            # Headers personalizados para mejor compatibilidad
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'es-ES,es;q=0.8,en-US;q=0.5,en;q=0.3',
                'Cache-Control': 'no-cache',
                'Pragma': 'no-cache'
            }
            
            # Intentar primero con requests
            content = None
            status_code = None
            use_playwright = False
            
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
                    if 'text/html' in content_type.lower():
                        initial_content = response.text
                    else:
                        # No necesitamos el contenido de recursos no HTML
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
                    initial_content = response.text
                    status_code = response.status_code

                # Revisar si debemos usar Playwright (decisión ligera)
                with PlaywrightHandler(headless=self.headless_mode) as pw:
                    use_playwright = (
                        pw._should_use_playwright(url, content_length, content_type)
                        or len(initial_content.strip()) < 1000
                    )  # Contenido muy pequeño podría ser JS
            except Exception as e:
                logger.warning(f"Request inicial falló, usando Playwright: {str(e)}")
                use_playwright = True

            # Si es necesario, usar Playwright
            if use_playwright:
                if progress_callback:
                    progress_callback(f"🎭 Usando Playwright para: {url}")
                
                try:
                    with PlaywrightHandler(headless=self.headless_mode) as pw:
                        # Esperar por selectores más comprehensivos y dar más tiempo
                        content, status_code = pw.get_page_content(
                            url,
                            wait_for_selectors=[
                                'h1', 'title',
                                'meta[name="description"]',
                                'div', 'main', 'article',  # Contenido principal
                                'nav', 'header', 'footer'  # Elementos estructurales
                            ],
                            post_load_wait=5  # Aumentar tiempo de espera para JS
                        )
                except Exception as e:
                    logger.error(f"Error con Playwright: {str(e)}")
                    if not content:  # Si no tenemos contenido de ninguna fuente
                        raise Exception("No se pudo obtener contenido")
            else:
                content = initial_content
            
            # Datos básicos de la página
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
            
            # Si tenemos contenido para analizar
            if content and (status_code == 200 or 300 <= status_code < 400):  # Aceptar redirecciones
                # El contenido ya está decodificado, solo necesitamos detectar la codificación para BeautifulSoup
                # Intentar determinar la codificación del contenido
                encoding = 'utf-8'  # Codificación por defecto
                
                # Intentar diferentes codificaciones si es necesario
                encodings_to_try = ['utf-8', 'utf-8-sig', 'utf-16', 'latin-1', 'iso-8859-1', 'cp1252']
                content_decoded = None
                
                for enc in encodings_to_try:
                    try:
                        if isinstance(content, str):
                            content_decoded = content
                            encoding = enc
                            break
                        if isinstance(content, bytes):
                            content_decoded = content.decode(enc)
                            encoding = enc
                            break
                    except Exception:
                        continue
                        
                if not content_decoded:
                    # Si todo falla, usar latin-1 que siempre funciona
                    content_decoded = content if isinstance(content, str) else content.decode('latin-1')
                    encoding = 'latin-1'
                    
                content = content_decoded
                
                # Crear parser más robusto
                soup = BeautifulSoup(content, 'html.parser', from_encoding=encoding)
                
                # Limpiar scripts y estilos para mejor análisis de texto
                for script in soup(['script', 'style']):
                    script.decompose()
                
                # Verificar si es contenido dinámico (JavaScript)
                if len(soup.text.strip()) < 100 and soup.find_all('script'):
                    if progress_callback:
                        progress_callback(f"⚠️ Detectado posible contenido dinámico en {url}")
                        
                # Limpiar el HTML para mejor análisis
                [x.extract() for x in soup.find_all('script')]
                [x.extract() for x in soup.find_all('style')]
                [x.extract() for x in soup.find_all('iframe')]

                # Intentar detectar el contenedor principal para extraer texto más representativo
                def _find_main_container(soup_obj):
                    # Priorizar <main>
                    main = soup_obj.find('main')
                    if main:
                        return main
                    # Buscar por ids/classes comunes que suelen contener el contenido principal
                    candidates = ['content', 'main', 'page', 'site', 'wrap', 'container', 'app', 'region', 'contenido']
                    for attr in ['id', 'class']:
                        for cand in candidates:
                            try:
                                found = soup_obj.find(attrs={attr: lambda v, c=cand: v and c in v.lower()})
                                if found:
                                    return found
                            except Exception:
                                continue
                    # Fallback al body
                    return soup_obj.find('body') or soup_obj

                main_container = _find_main_container(soup)
                
                # Extraer Meta Título
                title_tag = soup.find('title')
                if title_tag:
                    title_text = title_tag.get_text().strip()
                    page_data['Meta Titulo'] = title_text
                    page_data['Longitud Meta Titulo'] = len(title_text)
                    # Registrar para detección de duplicados
                    if title_text:
                        if title_text not in self.meta_titles:
                            self.meta_titles[title_text] = []
                        self.meta_titles[title_text].append(url)
                
                # Extraer Meta Description
                meta_desc = soup.find('meta', attrs={'name': 'description'})
                if meta_desc:
                    desc_text = meta_desc.get('content', '').strip()
                    page_data['Meta Description'] = desc_text
                    page_data['Longitud Meta Description'] = len(desc_text)
                    # Registrar para detección de duplicados
                    if desc_text:
                        if desc_text not in self.meta_desc:
                            self.meta_desc[desc_text] = []
                        self.meta_desc[desc_text].append(url)
                
                # Extraer H1s (con fallback a selectores/clases comunes si no hay etiquetas h1)
                h1_tags = soup.find_all('h1')
                if not h1_tags:
                    # Buscar por clases o ids que sugieran título
                    h1_tags = []
                    candidates = ['title', 'page-title', 'heading', 'hero-title', 'site-title', 'titulo', 'titulo-pagina']
                    for cand in candidates:
                        try:
                            found = soup.find(attrs={'class': lambda v, c=cand: v and c in v.lower()})
                            if found:
                                h1_tags.append(found)
                        except Exception:
                            continue
                    # role=heading (fallback)
                    if not h1_tags:
                        h1_role = soup.find(attrs={'role': 'heading'})
                        if h1_role:
                            h1_tags.append(h1_role)

                h1_texts = [h.get_text().strip() for h in h1_tags if h.get_text().strip()]
                if h1_texts:
                    page_data['H1'] = ' | '.join(h1_texts)
                    page_data['Cantidad H1'] = len(h1_texts)
                    # Registrar para detección de duplicados
                    for h1_text in h1_texts:
                        if h1_text not in self.h1s:
                            self.h1s[h1_text] = []
                        self.h1s[h1_text].append(url)
                
                # Extraer H2s con fallback a clases comunes
                h2_tags = soup.find_all('h2')
                if not h2_tags:
                    candidates2 = ['subtitle', 'sub-title', 'section-title', 'heading-2', 'subtitulo']
                    for cand in candidates2:
                        try:
                            founds = soup.find_all(attrs={'class': lambda v, c=cand: v and c in v.lower()})
                            for f in founds:
                                h2_tags.append(f)
                        except Exception:
                            continue

                if h2_tags:
                    page_data['H2'] = ' | '.join(h.get_text().strip() for h in h2_tags if h.get_text().strip())
                
                # Extraer Canonical
                canonical = soup.find('link', rel='canonical')
                if canonical:
                    page_data['Canonical'] = canonical.get('href', '')
                
                # Extraer Robots
                robots = soup.find('meta', attrs={'name': 'robots'})
                if robots:
                    page_data['Robots'] = robots.get('content', '')
                
                # Extraer hreflangs
                hreflangs = soup.find_all('link', rel='alternate', hreflang=True)
                for hreflang in hreflangs:
                    lang = hreflang.get('hreflang', '').lower()
                    href = hreflang.get('href', '')
                    if lang == 'es' or lang.startswith('es-'):
                        page_data['hreflang_es'] = href
                    elif lang == 'en' or lang.startswith('en-'):
                        page_data['hreflang_en'] = href
                    elif lang == 'pt' or lang.startswith('pt-'):
                        page_data['hreflang_pt'] = href
                
                # Extraer y contar palabras: preferir el contenedor principal
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
                words = len(text_content.split())
                page_data['Word Count'] = words
                
                # Extraer palabras clave (top 10 palabras más frecuentes, excluyendo stopwords)
                import re
                from collections import Counter
                
                # Lista básica de stopwords en español e inglés
                stopwords = {'de', 'la', 'que', 'el', 'en', 'y', 'a', 'los', 'del', 'las', 'un', 'por', 'con', 'una',
                           'su', 'para', 'es', 'al', 'lo', 'como', 'más', 'o', 'pero', 'sus', 'le', 'ha', 'me', 'si',
                           'sin', 'sobre', 'este', 'ya', 'entre', 'cuando', 'todo', 'esta', 'ser', 'son', 'dos', 'también',
                           'fue', 'había', 'era', 'muy', 'años', 'hasta', 'desde', 'está', 'mi', 'porque', 'qué', 'sólo',
                           'han', 'yo', 'hay', 'vez', 'puede', 'todos', 'así', 'nos', 'ni', 'parte', 'tiene', 'él',
                           'the', 'and', 'to', 'of', 'in', 'for', 'is', 'on', 'that', 'by', 'this', 'with', 'i', 'you',
                           'it', 'not', 'or', 'be', 'are', 'from', 'at', 'as', 'your', 'all', 'have', 'new', 'more',
                           'an', 'was', 'we', 'will', 'can', 'us', 'about', 'if', 'my', 'has', 'but', 'our', 'one',
                           'other', 'do', 'no', 'they', 'he', 'may', 'what', 'which', 'their', 'any', 'there', 'who'}
                
                # Extraer palabras del texto
                words = re.findall(r'\b\w+\b', text_content.lower())
                # Filtrar stopwords y palabras cortas
                content_words = [word for word in words if word not in stopwords and len(word) > 3]
                # Obtener las 10 palabras más frecuentes
                word_freq = Counter(content_words).most_common(10)
                page_data['Palabras Clave'] = ', '.join(word for word, _ in word_freq)
                
                # Procesar enlaces si está habilitado
                anchors = []
                if self.analyze_links:
                    source_domain = urlparse(url).netloc.replace('www.', '')
                    
                    # Buscar enlaces en todas las etiquetas relevantes
                    for element in soup.find_all(['a', 'area', 'link']):
                        href = element.get('href', '').strip()
                        if not href or href.startswith(('javascript:', 'data:', 'tel:', 'mailto:')):
                            continue
                            
                        try:
                            full_url = urljoin(url, href)
                            
                            # Verificar si es una URL válida
                            parsed_url = urlparse(full_url)
                            if not parsed_url.scheme or not parsed_url.netloc:
                                continue
                                
                            target_domain = parsed_url.netloc.replace('www.', '')
                            anchor_text = element.get_text().strip()
                            
                            # Determinar tipo de enlace
                            link_type = 'Interno' if source_domain == target_domain else 'Externo'
                            
                            # Verificar estado del enlace
                            link_status = self._check_link_status(full_url)
                            
                            # Guardar datos del enlace
                            link_data = {
                                'Source Page': url,
                                'Source Domain': source_domain,
                                'Target URL': full_url,
                                'Target Domain': target_domain,
                                'Domain Authority': '',  # Se dejará vacío por ahora
                                'Link Type': link_type,
                                'Anchor Text': anchor_text if anchor_text else '',
                                'Status': link_status['status'],
                                'Status Code': link_status.get('code', '')
                            }
                            self.links.append(link_data)
                            
                            if anchor_text:
                                anchors.append(anchor_text)
                            
                            # Si es un enlace interno y válido, agregarlo a la cola
                            if link_type == 'Interno' and self.is_valid_url(full_url):
                                # Respetar el modo de URLs específicas
                                if not self.specific_urls or full_url in self.specific_urls:
                                    self.add_url_to_queue(full_url)
                                    
                            # Procesar hreflangs
                            if element.get('hreflang'):
                                hreflang_url = urljoin(url, element['href'])
                                if self.is_valid_url(hreflang_url):
                                    self.add_url_to_queue(hreflang_url)
                                    
                        except Exception as e:
                            if progress_callback:
                                progress_callback(f"⚠️ Error procesando enlace en {url}: {str(e)}")
                
                # Guardar textos ancla únicos
                if anchors:
                    page_data['Anchor'] = ' | '.join(set(anchors))
                
                # Analizar imágenes si está habilitado
                if self.analyze_images:
                    # Buscar todas las imágenes incluyendo favicon si existe
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
                    
                    # Procesar imágenes normales
                    img_tags = soup.find_all('img')
                    for source in soup.find_all(['source', 'picture']):
                        if source.get('srcset'):
                            for src in source['srcset'].split(','):
                                src = src.strip().split()[0]  # Tomar URL sin el descriptor de tamaño
                                img = soup.new_tag('img')
                                img['src'] = src
                                img_tags.append(img)
                    
                    # Procesar cada imagen encontrada
                    for img in img_tags:
                        img_data = self._analyze_image(img, url)
                        if img_data:
                            self.images.append(img_data)
                
            self.results.append(page_data)
            time.sleep(self.delay)
            
        except Exception as e:
            if progress_callback:
                progress_callback(f"⚠️ Error analizando {url}: {str(e)}")
            
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
                
                # Si tenemos algún contenido, intentar extraer lo que se pueda
                if content:
                    try:
                        soup = BeautifulSoup(content, 'html.parser')
                        
                        # Intentar extraer título
                        title_tag = soup.find('title')
                        if title_tag:
                            page_data['Meta Titulo'] = title_tag.get_text().strip()
                            page_data['Longitud Meta Titulo'] = len(page_data['Meta Titulo'])
                        
                        # Intentar extraer meta description
                        meta_desc = soup.find('meta', attrs={'name': 'description'})
                        if meta_desc:
                            desc_text = meta_desc.get('content', '').strip()
                            page_data['Meta Description'] = desc_text
                            page_data['Longitud Meta Description'] = len(desc_text)
                        
                        # Intentar extraer H1s
                        h1_tags = soup.find_all('h1')
                        if h1_tags:
                            page_data['H1'] = ' | '.join(h.get_text().strip() for h in h1_tags if h.get_text().strip())
                            page_data['Cantidad H1'] = len(h1_tags)
                    except Exception:
                        pass  # Si falla el análisis parcial, usar los valores por defecto
                
                self.results.append(page_data)
                
            except Exception:
                # Si todo falla, agregar entrada mínima
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
            # Verificar límite solo si max_pages no es 1
            if self.max_pages != 1 and len(self.visited) >= self.max_pages:
                if progress_callback:
                    progress_callback(f"🎯 Alcanzado límite de {self.max_pages} páginas", {'completed': len(self.visited), 'total': total})
                break
                
            url = self.to_visit.popleft()
            # Normalizar URL antes de procesar
            url = self._normalize_url(url)
            if url not in self.visited:
                self.visited.add(url)
                self.crawl_page(url, progress_callback)
                
                if progress_callback:
                    # Calcular progreso y tiempos
                    elapsed_time = time.time() - self.start_time
                    pages_analyzed = len(self.visited)
                    
                    # Formatear tiempo transcurrido
                    hours = int(elapsed_time // 3600)
                    minutes = int((elapsed_time % 3600) // 60)
                    seconds = int(elapsed_time % 60)
                    time_str = f"{hours}h {minutes}m {seconds}s"
                    
                    # Status con detalles completos
                    status = f"📊 Progreso del análisis:\n"
                    status += f"   - Páginas analizadas: {pages_analyzed}\n"
                    status += f"   - Tiempo transcurrido: {time_str}\n"
                    status += f"   - URLs pendientes: {len(self.to_visit)}"
                    
                    progress_callback(status, {'completed': pages_analyzed, 'total': total, 'pending': len(self.to_visit)})
        
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
                total_time = time.time() - self.start_time
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
                        'Análisis Completo',
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
                    url = result['URL']
                    
                    # Páginas sin H1
                    if not result.get('H1') or result['H1'] == 'No tiene H1':
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
                            'Descripción': f'La página tiene {result["Cantidad H1"]} encabezados H1',
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
                            'Descripción': f'Meta Título tiene {result["Longitud Meta Titulo"]} caracteres (máx. recomendado: 60)',
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
