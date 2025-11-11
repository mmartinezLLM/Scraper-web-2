"""
Módulo de estilos para la interfaz gráfica del SEO Spider.
Contiene todas las configuraciones de temas y estilos de la aplicación.
"""

class ThemeColors:
    """Paletas de colores para los temas claro y oscuro."""
    
    class Dark:
        """Paleta de colores para el tema oscuro."""
        BG = '#1E1E1E'          # Fondo principal más oscuro
        FG = '#FFFFFF'          # Texto más brillante
        ENTRY_BG = '#2D2D2D'    # Fondo de entrada más contrastante
        ENTRY_FG = '#FFFFFF'    # Texto de entrada más brillante
        BUTTON_BG = '#3D3D3D'   # Botones más distinguibles
        BUTTON_FG = '#FFFFFF'   # Texto de botones más brillante
        SELECT_BG = '#4D4D4D'   # Color de selección
        BORDER = '#555555'      # Bordes más visibles
        HOVER_BG = '#4D4D4D'    # Color al pasar el mouse
        PRESS_BG = '#2D2D2D'    # Color al presionar
    
    class Light:
        """Paleta de colores para el tema claro."""
        BG = '#FFFFFF'          # Fondo blanco limpio
        FG = "#000000"          # Texto negro
        ENTRY_BG = '#F5F5F5'    # Fondo de entrada ligeramente gris
        ENTRY_FG = '#2C2C2C'    # Texto de entrada oscuro
        BUTTON_BG = '#F0F0F0'   # Botones sutilmente diferentes
        BUTTON_FG = '#2C2C2C'   # Texto de botones oscuro
        SELECT_BG = "#000000"   # Color de selección
        BORDER = '#D0D0D0'      # Bordes sutiles
        HOVER_BG = "#FFFFFF"    # Color al pasar el mouse
        PRESS_BG = '#D0D0D0'    # Color al presionar

class Fonts:
    """Configuraciones de fuentes para la interfaz."""
    FAMILY = 'Segoe UI'
    NORMAL_SIZE = 10
    HEADER_SIZE = 12
    TITLE_SIZE = 14

class StyleConfig:
    """Configuraciones de estilo para los widgets ttk."""
    
    @staticmethod
    def configure_styles(style, colors):
        """
        Configura los estilos para todos los widgets ttk.
        
        Args:
            style: Objeto ttk.Style
            colors: Objeto ThemeColors.Dark o ThemeColors.Light
        """
        # Eliminar bordes por defecto
        style.configure(".", borderwidth=0)
        # Estilos base
        style.configure('.', 
            background=colors.BG,
            foreground=colors.FG)
        
        # Frames y contenedores sin bordes
        style.configure('TFrame',
            background=colors.BG,
            borderwidth=0)
        style.layout('TFrame', [
            ('Frame.border', {'sticky': 'nswe', 'border': '0'})
        ])
        
        # Estilo especial para frames sin bordes absolutos

        # LabelFrame sin bordes
        style.configure('TLabelframe',
            background=colors.BG,
            borderwidth=0,
            relief='flat')
        style.configure('TLabelframe.Label',
            background=colors.BG,
            foreground=colors.FG,
            font=(Fonts.FAMILY, Fonts.NORMAL_SIZE))
        
        # Checkbox personalizado
        style.configure('Custom.TCheckbutton',
            background=colors.BG,
            foreground=colors.FG,
            font=(Fonts.FAMILY, Fonts.NORMAL_SIZE),
            padding=(10, 5))
        style.map('Custom.TCheckbutton',
            background=[('active', colors.BG),
                       ('pressed', colors.BG)])
        style.layout('TLabelframe', [
            ('Labelframe.border', {'sticky': 'nswe', 'border': '0'})
        ])
        
        # Etiquetas normales
        style.configure('TLabel',
            background=colors.BG,
            foreground=colors.FG,
            font=(Fonts.FAMILY, Fonts.NORMAL_SIZE))
        
        # Etiquetas de encabezado
        style.configure('Header.TLabel',
            background=colors.BG,
            foreground=colors.FG,
            font=(Fonts.FAMILY, Fonts.HEADER_SIZE, 'bold'))
            
        # Etiquetas de título
        style.configure('Title.TLabel',
            background=colors.BG,
            foreground=colors.FG,
            font=(Fonts.FAMILY, Fonts.TITLE_SIZE, 'bold'))
        
        # Entradas de texto
        style.configure('TEntry',
            fieldbackground=colors.ENTRY_BG,
            foreground=colors.ENTRY_FG,
            borderwidth=0)
        
        # Botones con efectos interactivos y sin bordes
        style.configure('TButton',
            background=colors.BUTTON_BG,
            foreground=colors.BUTTON_FG,
            borderwidth=0,
            relief="flat",
            padding=(10, 5))
            
        style.layout('TButton', [
            ('Button.padding', {'children': [
                ('Button.label', {'sticky': 'nswe'})
            ], 'sticky': 'nswe'})
        ])
            
        style.map('TButton',
            background=[('active', colors.HOVER_BG),
                       ('pressed', colors.PRESS_BG)])
        
        # Botón de tema
        style.configure('Theme.TButton',
            padding=5)
        
        # Configuración base del Notebook con colores del fondo
        style.configure('TNotebook', 
            background=colors.BG,
            bordercolor=colors.BG,
            lightcolor=colors.BG,
            darkcolor=colors.BG)
        
        # Layout básico del Notebook
        style.layout('TNotebook', [
            ('TNotebook.client', {'sticky': 'nswe'})
        ])
        
        # Configuración de las pestañas con colores fuertes para garantizar visibilidad
        style.configure('TNotebook.Tab',
            background=colors.BUTTON_BG,
            foreground=colors.FG,  # Siempre usar el color principal del texto
            padding=(10, 4),
            borderwidth=0)
        
        # Layout simple para las pestañas
        style.layout('TNotebook.Tab', [
            ('Notebook.tab', {'sticky': 'nswe',
                'children': [
                    ('Notebook.padding', {'side': 'top', 'sticky': 'nswe',
                        'children': [
                            ('Notebook.label', {'sticky': 'nswe'})
                        ]})
                ]})
        ])
        
        # Mapeo de colores para máximo contraste en las pestañas
        style.map('TNotebook.Tab',
            background=[
                ('selected', colors.BG),
                ('!selected', colors.BUTTON_BG)
            ],
            foreground=[
                ('selected', colors.FG),
                ('!selected', colors.FG),  # Siempre usar el color principal del texto
                ('active', colors.FG)
            ])
        
        # Spinbox con flechas mejoradas
        style.configure('TSpinbox',
            fieldbackground=colors.ENTRY_BG,
            foreground=colors.ENTRY_FG,
            background=colors.BG,
            borderwidth=0,
            relief='flat',
            arrowsize=13)
            
        # Configurar colores específicos para las flechas
        style.configure('TSpinbox.Vertical.TButton',
            background=colors.BUTTON_BG,
            foreground=colors.BUTTON_FG,
            borderwidth=0,
            relief='flat')
            
        # Layout mejorado del Spinbox    
        style.layout('TSpinbox', [
            ('Spinbox.field', {'side': 'top', 'sticky': 'we', 'border': '0',
                             'children': [
                                 ('Spinbox.padding', {'sticky': 'nswe', 'border': '0',
                                                    'children': [
                                                        ('Spinbox.textarea', {'sticky': 'nswe', 'border': '0'})
                                                    ]}),
                                 ('Spinbox.uparrow', {'side': 'right', 'sticky': 'nse', 'border': '0',
                                                    'children': [
                                                        ('Spinbox.uparrow.background', {'sticky': 'nswe'})
                                                    ]}),
                                 ('Spinbox.downarrow', {'side': 'right', 'sticky': 'se', 'border': '0',
                                                      'children': [
                                                          ('Spinbox.downarrow.background', {'sticky': 'nswe'})
                                                      ]})
                             ]})
        ])
        
        # Mapeo de colores para las flechas
        style.map('TSpinbox',
            fieldbackground=[
                ('readonly', colors.ENTRY_BG),
                ('disabled', colors.BG)
            ],
            foreground=[
                ('readonly', colors.ENTRY_FG),
                ('disabled', colors.FG)
            ],
            arrowcolor=[
                ('pressed', colors.PRESS_BG),
                ('active', colors.HOVER_BG),
                ('!disabled', colors.BUTTON_FG)
            ],
            background=[
                ('pressed', colors.PRESS_BG),
                ('active', colors.HOVER_BG),
                ('!disabled', colors.BUTTON_BG)
            ])
        
        # Entry sin bordes
        style.layout('TEntry', [
            ('Entry.field', {'border': '0', 'sticky': 'nswe',
                           'children': [
                               ('Entry.padding', {'sticky': 'nswe',
                                                'children': [
                                                    ('Entry.textarea', {'sticky': 'nswe'})
                                                ]})
                           ]})
        ])
        
        # Barra de progreso con colores personalizados
        style.configure("Horizontal.TProgressbar",
            troughcolor=colors.BG,
            bordercolor=colors.BG,
            background='#0583FF',  # Color azul principal
            troughrelief='flat',
            relief='flat',
            borderwidth=0,
            thickness=8)

        # Layout personalizado para la barra de progreso sin bordes
        style.layout('Horizontal.TProgressbar', [
            ('Horizontal.Progressbar.trough', {
                'sticky': 'nswe',
                'border': '0',
                'children': [
                    ('Horizontal.Progressbar.pbar', {
                        'side': 'left',
                        'sticky': 'ns'
                    })
                ]
            })
        ])

        # Mapeo de colores para cambio de estado
        style.map('Horizontal.TProgressbar',
                 background=[
                     ('active', '#E6484B'),    # Color rojo cuando activo
                     ('pressed', '#E6484B')    # Color rojo cuando presionado
                 ])

    @staticmethod
    def configure_text_widget(widget, colors):
        """
        Configura los estilos para widgets Text.
        
        Args:
            widget: Widget Text de tkinter
            colors: Objeto ThemeColors.Dark o ThemeColors.Light
        """
        widget.configure(
            background=colors.ENTRY_BG,
            foreground=colors.ENTRY_FG,
            insertbackground=colors.FG,
            selectbackground=colors.SELECT_BG,
            selectforeground=colors.ENTRY_FG,
            relief='flat',
            borderwidth=0,
            font=(Fonts.FAMILY, Fonts.NORMAL_SIZE))

    @staticmethod
    def configure_paned_widget(widget, colors):
        """
        Configura los estilos para widgets PanedWindow.
        
        Args:
            widget: Widget PanedWindow de tkinter
            colors: Objeto ThemeColors.Dark o ThemeColors.Light
        """
        widget.configure(
            background=colors.BG,
            sashwidth=2,
            sashrelief='flat')
