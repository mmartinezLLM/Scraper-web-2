"""
Módulo de interfaz gráfica para el SEO Spider.
"""
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import datetime
import os
import threading
import time
from ..core.seo_analyzer import SEOAnalyzer
from .styles import ThemeColors, StyleConfig

class SEOSpiderGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Herramienta SEO Spider - Analizador de Sitios Web BTS")
        
        # Configurar tamaño inicial y mínimo
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        initial_width = min(900, screen_width - 100)
        initial_height = min(750, screen_height - 100)
        self.initial_height = initial_height
        
        self.root.geometry(f"{initial_width}x{initial_height}")
        self.root.minsize(800, 600)  # Aumentado el tamaño mínimo
        
        # Configurar grid principal
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        self.is_dark_mode = False
        
        self.analyzer = None
        self.is_analyzing = False
        
        self.setup_ui()
    
    def setup_ui(self):
        """Configurar interfaz completamente responsiva usando PanedWindow vertical"""
        # Frame principal
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky="nsew")
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(0, weight=0)  # Fila para la barra superior
        main_frame.rowconfigure(1, weight=1)  # Fila para el contenido principal

        # Frame para la barra superior (título y botón de tema)
        header_frame = ttk.Frame(main_frame)
        header_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        header_frame.columnconfigure(1, weight=1)  # Columna del título se expande

        # Logotipo o ícono (emoji)
        logo_label = ttk.Label(header_frame, text="🔍", font=('Arial', 16))
        logo_label.grid(row=0, column=0, padx=(0, 10))

        # Título de la aplicación
        title_label = ttk.Label(header_frame, 
                               text="SEO Spider - Analizador de Sitios Web", 
                               font=('Arial', 12, 'bold'))
        title_label.grid(row=0, column=1, sticky="w")

        # Botón para cambiar tema con estilo mejorado
        style = ttk.Style()
        style.configure('Theme.TButton', padding=5)
        self.theme_button = ttk.Button(header_frame, 
                                     text="🌙", 
                                     command=self.toggle_theme, 
                                     width=3,
                                     style='Theme.TButton')
        self.theme_button.grid(row=0, column=2, sticky="e", padx=(10, 0))
        
        # Paned window vertical (top: notebook, bottom: progreso + botones + log)
        paned = tk.PanedWindow(main_frame, orient=tk.VERTICAL)
        paned.grid(row=1, column=0, sticky="nsew")
        
        # Top container (notebook)
        top_container = ttk.Frame(paned)
        top_container.columnconfigure(0, weight=1)
        top_container.rowconfigure(0, weight=1)
        
        # Configurar estilos para ttk
        self.style = ttk.Style(self.root)
        self.style.theme_use('clam')  # Usar un tema que permita configurar colores
        
        # Guardar widgets que necesitan cambio de color manual
        self.widgets_to_style = {
            'text': [],
            'paned': [paned]
        }

        # Bottom container (progreso, botones, log)
        bottom_container = ttk.Frame(paned)
        # Configurar el contenedor inferior para manejar correctamente el espacio
        bottom_container.columnconfigure(0, weight=1)
        bottom_container.rowconfigure(0, weight=0)  # Progress area
        bottom_container.rowconfigure(1, weight=1)  # Log area expandible
        
        paned.add(top_container, height=600)  # Dar más altura inicial al contenedor superior
        paned.add(bottom_container, height=200)  # Altura fija para el contenedor inferior
        
        # Inicialmente configurar el paned window para dar más espacio a la parte superior
        self.root.update_idletasks()
        paned.sash_place(0, 0, int(self.initial_height * 0.6))  # Aumentado a 80% para la parte superior
        
        # Crear notebook dentro del top_container
        self.notebook = ttk.Notebook(top_container)
        self.notebook.grid(row=0, column=0, sticky="nsew", pady=(0, 10))
        
        # Pestañas
        self.full_analysis_frame = ttk.Frame(self.notebook)
        self.specific_urls_frame = ttk.Frame(self.notebook)
        
        self.notebook.add(self.full_analysis_frame, text='Análisis Completo')
        self.notebook.add(self.specific_urls_frame, text='URLs Específicas')
        
        # Configurar las pestañas
        self.setup_full_analysis_tab()
        self.setup_specific_urls_tab()
        
        # Área de progreso (dentro de bottom_container)
        self.setup_progress_area(bottom_container)

        # Área de log (bottom_container)
        self.setup_log_area(bottom_container)

        # Vincular cambio de pestaña para mostrar/ocultar controles de progreso
        self.notebook.bind('<<NotebookTabChanged>>', self.on_tab_changed)
        # Inicializar visibilidad según la pestaña activa
        try:
            self.on_tab_changed(None)
        except Exception:
            pass
        
        # Intentar posicionar la división
        try:
            self.root.update_idletasks()
            # Reducir el espacio superior para compactar la interfaz
            desired_y = int(self.initial_height * 0.6)  # Aumentar el espacio superior
            paned.sash_place(0, 0, desired_y)
        except Exception:
            pass

        # Aplicar tema inicial
        self.apply_theme()

    def toggle_theme(self):
        """Alterna entre el modo claro y oscuro."""
        self.is_dark_mode = not self.is_dark_mode
        self.apply_theme()

    def apply_theme(self):
        """Aplica los colores del tema actual a todos los widgets."""
        colors = ThemeColors.Dark if self.is_dark_mode else ThemeColors.Light
        self.theme_button.config(text="☀️" if self.is_dark_mode else "🌙")
        
        # Aplicar estilos a través de StyleConfig
        StyleConfig.configure_styles(self.style, colors)
        
        # Aplicar a widgets text
        for widget in self.widgets_to_style['text']:
            StyleConfig.configure_text_widget(widget, colors)
                
        # Aplicar a widgets paned
        for widget in self.widgets_to_style['paned']:
            StyleConfig.configure_paned_widget(widget, colors)

    def on_tab_changed(self, event):
        """Mostrar u ocultar elementos según la pestaña activa.
        
        El log debe mostrarse en ambas pestañas, pero el botón de análisis completo
        solo en su pestaña correspondiente.
        """
        try:
            current_text = self.notebook.tab(self.notebook.select(), 'text')
        except Exception:
            return

        try:
            # Usar el mismo botón principal para ambos modos, cambiando label y comando
            if current_text == 'Análisis Completo':
                if hasattr(self, 'analyze_button'):
                    self.analyze_button.config(text='Iniciar Análisis Completo', command=self.start_full_analysis)
                    self.analyze_button.grid()
            else:
                # En la pestaña de URLs específicas reutilizamos el mismo botón
                if hasattr(self, 'analyze_button'):
                    self.analyze_button.config(text='Analizar URLs Específicas', command=self.start_specific_analysis)
                    self.analyze_button.grid()

            # El log siempre visible abajo
            if hasattr(self, 'log_frame'):
                self.log_frame.grid_configure(row=1)
        except Exception:
            pass

    def setup_full_analysis_tab(self):
        """Configurar pestaña de análisis completo"""
        # Configurar grid principal de 1 columna
        self.full_analysis_frame.columnconfigure(0, weight=1)
        
        # Título
        title_label = ttk.Label(self.full_analysis_frame,
                               text="Análisis Completo del Sitio",
                               style='Header.TLabel',
                               font=('Arial', 14, 'bold'))
        title_label.grid(row=0, column=0, sticky="w", pady=(20, 10), padx=20)

        # Frame para la URL
        url_frame = ttk.Frame(self.full_analysis_frame)
        url_frame.grid(row=1, column=0, sticky="ew", padx=20, pady=5)
        url_frame.columnconfigure(1, weight=1)
        ttk.Label(url_frame, text="URL del sitio:").grid(row=0, column=0, sticky="w", padx=(0, 10))
        self.url_entry = ttk.Entry(url_frame)
        self.url_entry.insert(0, "https://")
        self.url_entry.grid(row=0, column=1, sticky="ew")

        # Frame para configuración
        config_frame = ttk.Frame(self.full_analysis_frame)
        config_frame.grid(row=2, column=0, sticky="ew", pady=10, padx=20)
        config_frame.columnconfigure(1, weight=0) # No expandir spinbox

        ttk.Label(config_frame, text="Delay entre peticiones (seg):").grid(row=0, column=0, sticky="w", padx=(0, 5))
        self.delay_var = tk.StringVar(value="1")
        delay_spin = ttk.Spinbox(config_frame, from_=0.1, to=10, increment=0.1,
                                textvariable=self.delay_var, width=8)
        delay_spin.grid(row=0, column=1, sticky="w")

        # Frame para opciones
        options_frame = ttk.Frame(self.full_analysis_frame)
        options_frame.grid(row=3, column=0, sticky="w", pady=(5, 0), padx=20)
        
        ttk.Label(options_frame, text="Opciones:", style='TLabel').grid(row=0, column=0, sticky='w', pady=(0,5))
        
        self.analyze_images_var = tk.BooleanVar(value=True)
        self.analyze_links_var = tk.BooleanVar(value=True)

        ttk.Checkbutton(options_frame,
                       text="Analizar imágenes (ALT, title, peso)",
                       variable=self.analyze_images_var).grid(row=1, column=0, sticky='w', pady=2)
        ttk.Checkbutton(options_frame,
                       text="Analizar enlaces (internos/externos, rotos)",
                       variable=self.analyze_links_var).grid(row=2, column=0, sticky='w', pady=2)
    
    def setup_specific_urls_tab(self):
        """Configurar pestaña de URLs específicas"""
        # Configurar grid principal
        self.specific_urls_frame.columnconfigure(0, weight=1)
        
        # Ajustar las filas para distribuir el espacio
        self.specific_urls_frame.rowconfigure(0, weight=0)  # Título
        self.specific_urls_frame.rowconfigure(1, weight=1)  # Área de texto
        self.specific_urls_frame.rowconfigure(2, weight=0)  # Configuración
        self.specific_urls_frame.rowconfigure(3, weight=0)  # Opciones
        self.specific_urls_frame.rowconfigure(4, weight=0)  # Botones
        
        # Título con más espacio y tamaño de fuente aumentado
        title_label = ttk.Label(self.specific_urls_frame,
                               text="Análisis de URLs Específicas",
                               style='Header.TLabel',
                               font=('Arial', 14, 'bold'))  # Fuente más grande
        title_label.grid(row=0, column=0, sticky="w", pady=(20, 10), padx=20)
        
        # Frame para área de texto
        text_container = ttk.Frame(self.specific_urls_frame)
        text_container.grid(row=1, column=0, sticky="nsew", pady=0, padx=20)
        text_container.columnconfigure(0, weight=1)
        text_container.rowconfigure(1, weight=1)
        
        # Etiqueta
        ttk.Label(text_container, 
                 text="Ingresa las URLs a analizar (una por línea):",
                 font=('Arial', 10)).grid(row=0, column=0, sticky="w", pady=(0, 5))
        
        # Área de texto con scrollbar
        text_frame = ttk.Frame(text_container)
        text_frame.grid(row=1, column=0, sticky="nsew")
        text_frame.columnconfigure(0, weight=1)
        text_frame.rowconfigure(0, weight=1)

        self.urls_text = tk.Text(text_frame, height=20, font=('Consolas', 10))
        self.widgets_to_style['text'].append(self.urls_text)
        scrollbar = ttk.Scrollbar(text_frame, orient=tk.VERTICAL, command=self.urls_text.yview)
        self.urls_text.configure(yscrollcommand=scrollbar.set)
        
        self.urls_text.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        
        # Configuración
        config_frame = ttk.Frame(self.specific_urls_frame)
        config_frame.grid(row=2, column=0, sticky="ew", pady=10, padx=20)
        config_frame.columnconfigure(1, weight=1)
        
        # Delay
        ttk.Label(config_frame, text="Delay entre peticiones (seg):").grid(row=0, column=0, sticky="w", padx=(0, 5))
        self.specific_delay_var = tk.StringVar(value="1")
        specific_delay_spin = ttk.Spinbox(config_frame, from_=0.1, to=10, increment=0.1,
                                         textvariable=self.specific_delay_var, width=8)
        specific_delay_spin.grid(row=0, column=1, sticky="w")

        # Frame para opciones
        options_frame = ttk.Frame(self.specific_urls_frame)
        options_frame.grid(row=3, column=0, sticky="w", pady=(5, 0), padx=20)
        options_frame.columnconfigure(0, weight=1)

        # Label de opciones
        ttk.Label(options_frame, text="Opciones:", style='TLabel').grid(row=0, column=0, sticky='w', pady=(0,5))

        # Checkboxes
        self.specific_analyze_images_var = tk.BooleanVar(value=True)
        self.specific_analyze_links_var = tk.BooleanVar(value=True)
        
        ttk.Checkbutton(options_frame,
                       text="Analizar imágenes (ALT, title, peso)",
                       variable=self.specific_analyze_images_var).grid(row=1, column=0, sticky="w", pady=2)
        ttk.Checkbutton(options_frame,
                       text="Analizar enlaces (internos/externos, rotos)",
                       variable=self.specific_analyze_links_var).grid(row=2, column=0, sticky="w", pady=2)

        # Frame para botones
        action_frame = ttk.Frame(self.specific_urls_frame)
        action_frame.grid(row=4, column=0, sticky="ew", pady=(15,10), padx=20)
        action_frame.columnconfigure(0, weight=1)

        # Container para centrar botones
        button_container = ttk.Frame(action_frame)
        button_container.pack()

        # Solo botón de Limpiar URLs (el botón de análisis se maneja desde analyze_button principal)
        self.clear_urls_button = ttk.Button(button_container,
                                          text="Limpiar URLs",
                                          command=self.clear_specific_urls,
                                          width=15)
        self.clear_urls_button.pack(side=tk.LEFT, padx=5)
    
    def clear_specific_urls(self):
        """Limpia el área de texto de URLs específicas"""
        self.urls_text.delete(1.0, tk.END)
    
    def setup_progress_area(self, parent):
        """Configurar área de progreso"""
        # Contenedor principal para progreso y botones (guardado en self)
        self.progress_container = ttk.Frame(parent)
        self.progress_container.grid(row=0, column=0, sticky="ew", pady=(0,2))
        self.progress_container.columnconfigure(0, weight=1)

        # Frame superior para el botón de inicio
        btn_frame = ttk.Frame(self.progress_container)
        btn_frame.grid(row=0, column=0, sticky='ew', pady=(0, 4))
        btn_frame.columnconfigure(0, weight=1)

        # Botón iniciar análisis
        self.analyze_button = ttk.Button(btn_frame,
                                       text="Iniciar Análisis Completo",
                                          command=self.start_full_analysis,
                                          width=30)  # Aumentado más el ancho para mostrar todo el texto
        self.analyze_button.grid(row=0, column=0)

        # Frame para estado y barra de progreso
        progress_frame = ttk.LabelFrame(self.progress_container, text="Estado del Análisis", style="Options.TLabelframe")
        progress_frame.grid(row=1, column=0, sticky="ew", padx=10)
        progress_frame.columnconfigure(0, weight=1)

        self.progress_label = ttk.Label(progress_frame, text="🟢 Listo para analizar", padding=(5,5))
        self.progress_label.grid(row=0, column=0, sticky="w")

        # Frame para la barra de progreso animada
        progress_bar_frame = ttk.Frame(progress_frame)
        progress_bar_frame.grid(row=1, column=0, sticky="ew", padx=5, pady=(0,5))
        progress_bar_frame.columnconfigure(0, weight=1)

        # Barra de progreso principal
        self.progress = ttk.Progressbar(progress_bar_frame, mode='determinate', style='Animated.Horizontal.TProgressbar')
        self.progress.grid(row=0, column=0, sticky="ew")

        # Configurar estilo animado para la barra de progreso
        style = ttk.Style()
        style.configure('Animated.Horizontal.TProgressbar', 
                        background='#2196f3',  # Azul material design
                        troughcolor='#e0e0e0',  # Gris claro
                        thickness=15)  # Hacer la barra más gruesa

        # Iniciar la animación de la barra
        self.progress_animation_frame = 0
        # Mezcla suave de azules a rojos y viceversa
        self.progress_colors = [

            '#2196f3',  # Azul material
            '#1e88e5',  # Azul oscuro
            "#0c61ac",  # Azul mas oscuro
            '#f44336',  # Rojo material
            '#e53935',  # Rojo oscuro
            '#d32f2f',  # Rojo más oscuro
            '#e53935',  # Rojo oscuro
            '#f44336',  # Rojo material
            "#0c61ac",  # Azul mas oscuro
            '#1e88e5',  # Azul oscuro
            '#2196f3',  # Azul material
        ]
        self.update_progress_animation()
        
        # Frame para los botones de control (Detener y Exportar)
        control_buttons_frame = ttk.Frame(self.progress_container)
        control_buttons_frame.grid(row=2, column=0, sticky="ew", pady=(5,0))
        control_buttons_frame.columnconfigure(0, weight=1)

        # Frame interno para centrar los botones
        buttons_inner_frame = ttk.Frame(control_buttons_frame)
        buttons_inner_frame.grid(row=0, column=0)

        # Botones de control
        self.stop_button = ttk.Button(buttons_inner_frame,
                                    text="Detener Análisis",
                                    command=self.toggle_pause_resume,
                                    state=tk.DISABLED,
                                    width=15)
        self.stop_button.pack(side=tk.LEFT, padx=5)

        self.export_button = ttk.Button(buttons_inner_frame,
                                      text="Exportar Excel",
                                      command=self.export_report,
                                      state=tk.DISABLED,
                                      width=15)
        self.export_button.pack(side=tk.LEFT, padx=5)
    
    def setup_buttons_area(self, parent):
        """Configurar área de botones"""
        # Esta función ya no se usa, los botones se movieron al área de progreso
        pass
    
    def setup_log_area(self, parent):
        """Configurar área de log"""
        # Configurar el peso de las filas en el parent
        parent.rowconfigure(0, weight=0)  # Progress area con botones (altura fija)
        parent.rowconfigure(1, weight=1)  # Log area (expandible)
        
        log_frame = ttk.Frame(parent)
        # Guardar referencia para poder reposicionar cuando se cambie de pestaña
        self.log_frame = log_frame
        # Reducir el padding superior ya que los botones están en el área de progreso
        log_frame.grid(row=1, column=0, sticky="nsew", pady=(10, 0))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(1, weight=1)  # Hacer que el área de texto sea expandible

        # Etiqueta del log
        ttk.Label(log_frame, text="Log de Actividad:").grid(row=0, column=0, sticky="w", pady=(0, 5))

        # Frame para el texto del log
        log_text_frame = ttk.Frame(log_frame)
        log_text_frame.grid(row=1, column=0, sticky="nsew")
        log_text_frame.columnconfigure(0, weight=1)
        log_text_frame.rowconfigure(0, weight=1)

        # Configurar el área de texto con altura más pequeña
        self.log_text = tk.Text(log_text_frame, wrap=tk.WORD, height=4)  # Reducida a 4 líneas
        self.widgets_to_style['text'].append(self.log_text)
        log_scrollbar = ttk.Scrollbar(log_text_frame, orient=tk.VERTICAL, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scrollbar.set)

        self.log_text.grid(row=0, column=0, sticky="nsew")
        log_scrollbar.grid(row=0, column=1, sticky="ns")
    
    def start_full_analysis(self):
        """Iniciar el análisis completo"""
        url = self.url_entry.get().strip()
        
        if url == "https://" or not url:
            messagebox.showerror("Error", "Por favor, ingresa una URL válida")
            return
        
        # Asegurarse de que la URL tenga el prefijo correcto
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
            self.url_entry.delete(0, tk.END)
            self.url_entry.insert(0, url)
        
        try:
            delay = float(self.delay_var.get())
        except ValueError:
            messagebox.showerror("Error", "Por favor, ingresa un valor válido para delay")
            return
        
        # Usar max_pages=1 (sin límite) por defecto para análisis completo
        max_pages = 1
        self.start_analysis(url, max_pages, delay)
    
    def start_specific_analysis(self):
        """Iniciar el análisis de URLs específicas"""
        urls_text = self.urls_text.get(1.0, tk.END).strip()
        if not urls_text:
            messagebox.showerror("Error", "Por favor, ingresa al menos una URL")
            return

        urls = [u.strip() for u in urls_text.split('\n') if u.strip()]
        valid_urls = []
        for u in urls:
            if not u.startswith(('http://', 'https://')):
                u = 'https://' + u
            valid_urls.append(u)

        base_url = valid_urls[0]
        max_pages = len(valid_urls)
        delay = float(self.specific_delay_var.get())

        # Llamar a start_analysis pasando los flags de esta pestaña sin
        # sobreescribir las variables globales de la pestaña de análisis completo.
        self.start_analysis(
            base_url,
            max_pages,
            delay,
            specific_urls=valid_urls,
            analyze_images=self.specific_analyze_images_var.get(),
            analyze_links=self.specific_analyze_links_var.get()
        )
    
    def start_analysis(self, base_url, max_pages, delay, specific_urls=None, analyze_images=None, analyze_links=None):
        """Iniciar el análisis (común para ambos modos)"""
        self.log_text.delete(1.0, tk.END)
        
        self.is_analyzing = True
        self.analyze_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)
        self.export_button.config(state=tk.DISABLED)
        
        try:
            self.stop_button.config(text="Detener Análisis", state=tk.NORMAL)
        except Exception:
            pass
        
        # Configurar la barra de progreso
        self.progress['value'] = 0
        
        # Ajustes según el modo (con o sin límite)
        if max_pages == 1:
            # Modo sin límite: iniciar con un valor base razonable
            self.progress['maximum'] = 100  # Valor inicial que se ajustará dinámicamente
            self.progress_label.config(text="🔄 Preparando búsqueda completa del dominio (sin límite)...")
        else:
            # Modo con límite: usar el número máximo de páginas
            self.progress['maximum'] = max_pages
            self.progress_label.config(text=f"🔄 Preparando análisis ({max_pages} páginas máximo)")

        # Obtener estados de los checkboxes (permitir overrides desde caller)
        if analyze_images is None:
            analyze_images = self.analyze_images_var.get()
        if analyze_links is None:
            analyze_links = self.analyze_links_var.get()
        
        # Mensaje inicial simplificado
        self.log_message("🚀 Iniciando análisis...")
        
        # Log de opciones seleccionadas
        self.log_message(f"📝 Opciones seleccionadas:")
        self.log_message(f"   - Analizar imágenes: {'Sí' if analyze_images else 'No'}")
        self.log_message(f"   - Analizar enlaces: {'Sí' if analyze_links else 'No'}")
        
        # Asegurarse de que los valores booleanos sean correctos
        analyze_images_val = bool(analyze_images)
        analyze_links_val = bool(analyze_links)
        
        print(f"GUI: Creando SEOAnalyzer con opciones:")
        print(f"- analyze_images: {analyze_images_val}")
        print(f"- analyze_links: {analyze_links_val}")
        
        self.analyzer = SEOAnalyzer(
            base_url, 
            max_pages=max_pages, 
            delay=delay, 
            specific_urls=specific_urls,
            headless_mode=True,
            analyze_images=analyze_images_val,
            analyze_links=analyze_links_val
        )
        
        thread = threading.Thread(target=self.run_analysis)
        thread.daemon = True
        thread.start()
    
    def run_analysis(self):
        """Ejecutar el análisis en el hilo separado"""
        self.analyzer.crawl_site(
            progress_callback=self.update_progress,
            completion_callback=self.analysis_complete
        )
    
    def update_progress(self, message, progress_data=None):
        """Actualizar el progreso y el log con mensajes simplificados"""
        # Si el mensaje contiene múltiples líneas, insertarlas una por línea
        logged_multiline = False
        try:
            if isinstance(message, str) and "\n" in message:
                for line in message.splitlines():
                    # Mantener incluso líneas vacías para separación visual
                    try:
                        self.log_message(line)
                    except Exception:
                        pass
                logged_multiline = True
        except Exception:
            logged_multiline = False

        # Normalizar mensaje a texto para evitar errores si se pasa otro tipo
        try:
            message_text = message if isinstance(message, str) else (str(message) if message is not None else '')
        except Exception:
            message_text = ''

        # Lista de términos técnicos para filtrar
        technical_terms = [
            "Status Code:", "Headers:", "Content preview:",
            "Contenido dinámico", "playwright.",
            "Renderizado con Playwright",
            "Data from this session",
            "Cannot read properties"
        ]
        
        # No mostrar mensajes que contengan términos técnicos
        if any(term in message_text for term in technical_terms):
            return
            
        # Simplificar mensajes de análisis (si no venían ya separadas en varias líneas)
        if (not logged_multiline) and "Analizando" in message_text:
            url = message_text.split("Analizando")[-1].strip()
            self.log_message(f"🔍 Analizando: {url}")
            return
            
        # Para otros mensajes importantes, mostrarlos simplificados
        if (not logged_multiline) and message_text.strip() and not message_text.startswith(("📡", "🔍", "📄", "⚙️")):
            self.log_message(message_text)
        
        # Actualizar barra de progreso
        if progress_data and 'completed' in progress_data and 'total' in progress_data:
            completed = progress_data['completed']
            total = progress_data['total']
            
            if (progress_data.get('total') == float('inf') or 
                (hasattr(self.analyzer, 'max_pages') and self.analyzer.max_pages == 1)):  # Modo sin límite
                # En modo sin límite, ajustamos la barra de progreso dinámicamente
                if completed >= self.progress['maximum']:
                    # Si superamos el máximo, duplicamos el tamaño de la barra
                    self.progress['maximum'] = max(1000, completed * 2)
                
                self.progress['value'] = completed
                pending = len(self.analyzer.to_visit) if hasattr(self.analyzer, 'to_visit') else 0
                self.progress_label.config(text=f"⏳ URLs analizadas: {completed} | Pendientes: {pending}")
            elif total and total > 0:
                # Modo con límite
                percentage = (completed / total) * 100
                self.progress['value'] = completed
                self.progress_label.config(text=f"⏳ Progreso: {completed}/{total} ({percentage:.1f}%)")
            else:
                # Fallback por si no hay total definido
                self.progress_label.config(text=f"⏳ URLs analizadas: {completed}")
                self.progress['value'] = completed
    
    def analysis_complete(self):
        """Callback cuando el análisis se completa"""
        self.is_analyzing = False
        self.root.after(0, self.finish_analysis)
    
    def finish_analysis(self):
        """Finalizar el análisis en el hilo principal"""
        try:
            self.progress['value'] = self.progress['maximum']
        except Exception:
            pass
        self.analyze_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)
        self.export_button.config(state=tk.NORMAL)
        try:
            self.stop_button.config(text="Detener Análisis", state=tk.DISABLED)
        except Exception:
            pass
        
        self.progress_label.config(text="✅ Análisis completado")
        
        # Calcular estadísticas finales
        if self.analyzer:
            total_pages = len(self.analyzer.visited) if hasattr(self.analyzer, 'visited') else 0
            elapsed_time = time.time() - self.analyzer.start_time if hasattr(self.analyzer, 'start_time') else 0
            elapsed_str = f"{int(elapsed_time // 60)}m {int(elapsed_time % 60)}s"
            
            status = "✅ Análisis completado\n"
            status += f"   📊 Total páginas analizadas: {total_pages}\n"
            status += f"   ⏱️ Tiempo total: {elapsed_str}"
            self.log_message(status)
        else:
            self.log_message("✅ Análisis completado")

    def save_snapshot(self):
        """Guardar snapshot parcial del análisis actual sin interacción del usuario.

        Devuelve la ruta del archivo guardado o None si falla.
        """
        if not self.analyzer:
            return None
            
        if not hasattr(self.analyzer, 'results') or not self.analyzer.results:
            return None

        import pandas as pd
        from pathlib import Path

        try:
            # Crear directorio snapshots si no existe
            snapshots_dir = Path("snapshots")
            snapshots_dir.mkdir(exist_ok=True)

            # Generar nombre único para el archivo
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            domain = self.analyzer.base_url.replace("http://", "").replace("https://", "").split("/")[0]
            filename = snapshots_dir / f"snapshot_{domain}_{timestamp}.xlsx"

            with pd.ExcelWriter(filename, engine='openpyxl') as writer:
                # Detalles por página
                if self.analyzer.results:
                    df = pd.DataFrame(self.analyzer.results)
                    if not df.empty:
                        # Ordenar por fecha de análisis
                        if 'Fecha Análisis' in df.columns:
                            df = df.sort_values('Fecha Análisis', ascending=False)
                        df.to_excel(writer, sheet_name='Detalles por Página', index=False)
                        self.log_message(f"   ✓ Guardados detalles de {len(df)} páginas")

                # Imágenes (usar la colección actual del analyzer)
                if hasattr(self.analyzer, 'images') and self.analyzer.images:
                    img_df = pd.DataFrame(self.analyzer.images)
                    # Deduplicar por página origen y URL de imagen
                    if not img_df.empty:
                        if 'Página Origen' in img_df.columns and 'URL Imagen' in img_df.columns:
                            img_df = img_df.drop_duplicates(subset=['Página Origen', 'URL Imagen'])
                        img_df.to_excel(writer, sheet_name='Imágenes', index=False)
                        self.log_message(f"   ✓ Guardados detalles de {len(img_df)} imágenes")

                # Enlaces (usar la colección actual del analyzer)
                if hasattr(self.analyzer, 'links') and self.analyzer.links:
                    links_df = pd.DataFrame(self.analyzer.links)
                    if not links_df.empty:
                        links_df.to_excel(writer, sheet_name='Enlaces Detallados', index=False)
                        self.log_message(f"   ✓ Guardados detalles de {len(links_df)} enlaces")

                # Resumen detallado
                try:
                    total_pages = len(self.analyzer.results)
                    total_broken = len(self.analyzer.broken_links) if hasattr(self.analyzer, 'broken_links') else 0
                    total_redirects = len(self.analyzer.redirected_urls) if hasattr(self.analyzer, 'redirected_urls') else 0
                    total_images = len(self.analyzer.images) if hasattr(self.analyzer, 'images') else 0
                    total_links = len(self.analyzer.links) if hasattr(self.analyzer, 'links') else 0
                    
                    summary = {
                        'Métrica': [
                            'Páginas analizadas',
                            'Imágenes encontradas',
                            'Enlaces analizados',
                            'Enlaces rotos',
                           
                            'URLs redirigidas',
                            'Estado',
                            'Fecha snapshot'
                        ],
                        'Valor': [
                            total_pages,
                            total_images,
                            total_links,
                            total_broken,
                            total_redirects,
                            'Parcial' if self.analyzer.to_visit else 'Completo',
                            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        ]
                    }
                    pd.DataFrame(summary).to_excel(writer, sheet_name='Resumen', index=False)
                    self.log_message("   ✓ Guardado resumen del análisis")
                except Exception as e:
                    self.log_message(f"   ⚠️ Error guardando resumen: {str(e)}")

            return filename
            
        except Exception as e:
            error_msg = f"❌ Error guardando snapshot: {str(e)}"
            if "Permission denied" in str(e):
                error_msg += "\nAsegúrate de que el archivo no esté abierto en Excel."
            self.log_message(error_msg)
            return None
    
    def stop_analysis(self):
        """Detener el análisis"""
        if not self.analyzer:
            return
            
        if not self.is_analyzing:
            return
            
        try:
            # Detener el crawler
            self.analyzer.stop_crawling()
            self.is_analyzing = False
            
            # Actualizar estado visual
            self.progress_label.config(text="⏸️ Análisis pausado...")
            self.stop_button.config(text="Reanudar Análisis", state=tk.NORMAL)
            self.export_button.config(state=tk.NORMAL)
            self.analyze_button.config(state=tk.NORMAL)

            # Guardar snapshot
            snapshot_path = self.save_snapshot()
            if snapshot_path:
                self.log_message("💾 Resultados parciales guardados en:")
                self.log_message(f"   {snapshot_path}")
                
            # Mostrar estadísticas
            total_pages = len(self.analyzer.visited) if hasattr(self.analyzer, 'visited') else 0
            urls_pending = len(self.analyzer.to_visit) if hasattr(self.analyzer, 'to_visit') else 0
            elapsed_time = time.time() - self.analyzer.start_time if hasattr(self.analyzer, 'start_time') else 0
            elapsed_str = f"{int(elapsed_time // 60)}m {int(elapsed_time % 60)}s"
            
            status = "⏸️ Análisis pausado\n"
            status += f"   📊 Páginas analizadas: {total_pages}\n"
            if urls_pending > 0:
                status += f"   🔄 URLs pendientes: {urls_pending}\n"
            status += f"   ⏱️ Tiempo transcurrido: {elapsed_str}"
            self.log_message(status)
            
        except Exception as e:
            self.log_message(f"❌ Error al detener el análisis: {str(e)}")
            # Asegurar que la interfaz quede en estado consistente
            self.is_analyzing = False
            self.stop_button.config(text="Reanudar Análisis", state=tk.NORMAL)
            self.analyze_button.config(state=tk.NORMAL)

    def resume_analysis(self):
        """Reanudar un análisis previamente detenido."""
        if not self.analyzer:
            messagebox.showerror("Error", "No se puede reanudar: no hay un análisis activo.")
            return

        if not hasattr(self.analyzer, 'to_visit') or not self.analyzer.to_visit:
            messagebox.showinfo("Info", "No hay URLs pendientes para reanudar el análisis.")
            # Actualizar estado visual para reflejar finalización
            self.progress_label.config(text="✅ Análisis completado")
            self.stop_button.config(state=tk.DISABLED)
            return

        try:
            # Preparar la interfaz
            self.progress_label.config(text="🔄 Reanudando análisis...")
            self.stop_button.config(text="Detener Análisis", state=tk.NORMAL)
            self.export_button.config(state=tk.DISABLED)
            self.analyze_button.config(state=tk.DISABLED)
            
            # Reanudar el crawler (restaurar estado desde el analyzer)
            resumed = False
            try:
                resumed = self.analyzer.resume_crawling()
            except Exception:
                resumed = False

            if not resumed:
                messagebox.showerror("Error", "No se pudo reanudar el análisis desde el estado guardado.")
                # Asegurar estado de interfaz
                self.is_analyzing = False
                self.stop_button.config(text="Reanudar Análisis", state=tk.NORMAL)
                self.analyze_button.config(state=tk.NORMAL)
                return
            self.is_analyzing = True
            
            # Mostrar estadísticas de reanudación
            total_pages = len(self.analyzer.visited) if hasattr(self.analyzer, 'visited') else 0
            urls_pending = len(self.analyzer.to_visit)
            
            status = "▶️ Reanudando análisis\n"
            status += f"   📊 Páginas analizadas: {total_pages}\n"
            status += f"   🔄 URLs pendientes: {urls_pending}"
            self.log_message(status)

            # Iniciar thread de análisis
            thread = threading.Thread(target=self.run_analysis)
            thread.daemon = True
            thread.start()
            
        except Exception as e:
            self.log_message(f"❌ Error al reanudar el análisis: {str(e)}")
            # Asegurar que la interfaz quede en estado consistente
            self.is_analyzing = False
            self.stop_button.config(text="Reanudar Análisis", state=tk.NORMAL)
            self.analyze_button.config(state=tk.NORMAL)

    def update_progress_animation(self):
        """Actualiza la animación de la barra de progreso"""
        if hasattr(self, 'progress'):
            # Solo animar si está en proceso de análisis
            if self.is_analyzing:
                # Rotar colores
                current_color = self.progress_colors[self.progress_animation_frame % len(self.progress_colors)]
                self.style.configure('Animated.Horizontal.TProgressbar', background=current_color)
                self.progress_animation_frame += 1
                
                # Si está cerca del final, agregar efecto de pulso
                if self.progress['value'] > 0.9 * self.progress['maximum']:
                    self.style.configure('Animated.Horizontal.TProgressbar', thickness=16)
                else:
                    self.style.configure('Animated.Horizontal.TProgressbar', thickness=15)

            # Programar siguiente actualización con un intervalo más largo para una transición más suave
            self.root.after(250, self.update_progress_animation)

    def toggle_pause_resume(self):
        """Toggle entre detener y reanudar análisis."""
        if self.is_analyzing:
            self.stop_analysis()
        else:
            self.resume_analysis()
    
    def log_message(self, message):
        """Añadir mensaje al log"""
        self.log_text.insert(tk.END, f"{message}\n")
        self.log_text.see(tk.END)
        self.root.update_idletasks()
    
    def export_report(self):
        """Exportar reporte a Excel"""
        if not (self.analyzer and self.analyzer.results):
            messagebox.showwarning("Advertencia", "No hay datos para exportar. Ejecuta un análisis primero.")
            return

        try:
            pending = bool(self.analyzer.to_visit)
        except Exception:
            pending = False

        if pending and not self.is_analyzing:
            confirm = messagebox.askyesno("Exportar resultados parciales",
                                          "El análisis está detenido y quedan URLs pendientes. ¿Deseas exportar los resultados parciales actuales?")
            if not confirm:
                return

        filename = self.analyzer.generate_report(progress_callback=self.log_message)
        if filename:
            folder_path = os.path.dirname(os.path.abspath(filename))
            messagebox.showinfo("Éxito", f"Reporte guardado como:\n{filename}")
            try:
                if os.path.exists(folder_path):
                    os.startfile(folder_path)
            except Exception as e:
                self.log_message(f"❌ Error al abrir la carpeta: {str(e)}")


