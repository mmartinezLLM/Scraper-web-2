from PIL import Image
import os

try:
    # Obtener la ruta del directorio actual
    current_dir = os.path.dirname(os.path.abspath(__file__))
    webp_path = os.path.join(current_dir, 'scraper.ico.webp')
    ico_path = os.path.join(current_dir, 'scraper.ico')

    # Abrir la imagen webp
    print(f"Abriendo imagen desde: {webp_path}")
    img = Image.open(webp_path)
    
    # Convertir a RGB si es necesario
    if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
        img = img.convert('RGBA')
    else:
        img = img.convert('RGB')

    # Redimensionar a tamaños comunes de iconos
    icon_sizes = [(16,16), (32,32), (48,48), (64,64), (128,128), (256,256)]
    
    # Crear versiones del icono en diferentes tamaños
    img_list = []
    for size in icon_sizes:
        resized_img = img.resize(size, Image.Resampling.LANCZOS)
        img_list.append(resized_img)

    # Guardar como ICO con múltiples tamaños
    print(f"Guardando icono en: {ico_path}")
    img_list[0].save(ico_path, format='ICO', sizes=icon_sizes, append_images=img_list[1:])
    print("✅ Conversión completada exitosamente")

except Exception as e:
    print(f"❌ Error durante la conversión: {str(e)}")