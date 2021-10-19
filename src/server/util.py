import base64
from io import BytesIO

from PIL import Image


def convert_pil_image_to_base64(img: Image) -> str:
    buffered = BytesIO()
    img.save(buffered, format="png")
    img_str = base64.b64encode(buffered.getvalue())
    img_str = f'data:image/png;base64,{img_str.decode()}'
    return img_str
