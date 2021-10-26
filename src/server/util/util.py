import base64
import json
from io import BytesIO
from pathlib import Path

import cv2
import h5py
import numpy as np
from PIL import Image


def convert_pil_image_to_base64(img: Image) -> str:
    buffered = BytesIO()
    img.save(buffered, format="png")
    img_str = base64.b64encode(buffered.getvalue())
    img_str = f'data:image/png;base64,{img_str.decode()}'
    return img_str


def get_roi_contours(experiment_id: str, current_roi_id: str,
                      include_all_rois=True, reshape_contours_to_list=True):
    current_roi_id = int(current_roi_id)

    artifact_dir = Path('/allen/aibs/informatics/danielsf'
                        '/classifier_prototype_data')
    artifact_path = artifact_dir / f'{experiment_id}_classifier_artifacts.h5'
    with h5py.File(artifact_path, 'r') as f:
        rois = json.loads((f['rois'][()]))
        roi_color_map = json.loads(f['roi_color_map'][()])

    all_contours = []

    for roi in rois:
        mask = roi['mask']
        x = roi['x']
        y = roi['y']
        width = roi['width']
        height = roi['height']
        id = roi['id']

        if not include_all_rois:
            if id != current_roi_id:
                continue

        blank = np.zeros((512, 512), dtype='uint8')
        blank[y:y + height, x:x + width] = mask
        contours, _ = cv2.findContours(blank, cv2.RETR_EXTERNAL,
                                       cv2.CHAIN_APPROX_NONE)
        if reshape_contours_to_list:
            contours = [
                x.reshape(x.shape[0], 2).tolist() for x in contours
            ]
        color = (255, 0, 0) if id == current_roi_id else roi_color_map[str(id)]
        for contour in contours:
            all_contours.append({
                'contour': contour,
                'color': color,
                'id': id
            })
    return all_contours


def get_trace(experiment_id: str, roi_id: str):
    artifact_dir = Path('/allen/aibs/informatics/danielsf'
                        '/classifier_prototype_data')
    artifact_path = artifact_dir / f'{experiment_id}_classifier_artifacts.h5'

    with h5py.File(artifact_path, 'r') as f:
        trace = (f['traces'][roi_id][()])
    return trace



