import base64
import json
from io import BytesIO
from pathlib import Path
from typing import Dict

import cv2
import h5py
import numpy as np
from PIL import Image
from flask import current_app

from src.server.database.schemas import JobRegion


def _is_roi_within_region(roi: Dict, region: JobRegion,
                          field_of_view_dimension=(512, 512)):
    """Returns whether an roi is within a region. An ROI is considered
    within a region if the mask intersects with the region"""
    region_mask = np.zeros(field_of_view_dimension, dtype='uint8')
    region_mask[region.x:region.x+region.width,
                region.y:region.y+region.height] = 1

    roi_mask = np.zeros(field_of_view_dimension, dtype='uint8')
    roi_mask[roi['y']:roi['y']+roi['height'],
             roi['x']:roi['x']+roi['width']] = roi['mask']

    intersection = roi_mask * region_mask

    return intersection.sum() > 1


def convert_pil_image_to_base64(img: Image) -> str:
    buffered = BytesIO()
    img.save(buffered, format="png")
    img_str = base64.b64encode(buffered.getvalue())
    img_str = f'data:image/png;base64,{img_str.decode()}'
    return img_str


def get_roi_contours(experiment_id: str, region: JobRegion,
                     reshape_contours_to_list=True):
    """Gets all ROIs within a given region of the field of view
    :param experiment_id:
        experiment id
    :param region:
        region to get contours for
    :param reshape_contours_to_list:
    :return:
        dict with keys
            - contour: list of contour x, y coordinates
            - color: color of contour
            - id: roi id
            - experiment_id: experiment id
    """
    artifact_path = get_artifacts_path(experiment_id=experiment_id)
    with h5py.File(artifact_path, 'r') as f:
        rois = json.loads((f['rois'][()]))
        roi_color_map = json.loads(f['roi_color_map'][()])

    all_contours = []

    for roi in rois:
        if not _is_roi_within_region(roi=roi, region=region):
            continue

        mask = roi['mask']
        x = roi['x']
        y = roi['y']
        width = roi['width']
        height = roi['height']
        id = roi['id']

        blank = np.zeros((512, 512), dtype='uint8')
        blank[y:y + height, x:x + width] = mask
        contours, _ = cv2.findContours(blank, cv2.RETR_EXTERNAL,
                                       cv2.CHAIN_APPROX_NONE)
        if reshape_contours_to_list:
            contours = [
                x.reshape(x.shape[0], 2).tolist() for x in contours
            ]
        color = roi_color_map[str(id)]
        for contour in contours:
            all_contours.append({
                'contour': contour,
                'color': color,
                'id': id,
                'experiment_id': experiment_id
            })
    return all_contours


def get_trace(experiment_id: str, roi_id: str):
    artifact_path = get_artifacts_path(experiment_id=experiment_id)

    with h5py.File(artifact_path, 'r') as f:
        trace = (f['traces'][roi_id][()])
    return trace


def get_artifacts_path(experiment_id: str):
    artifact_dir = Path(current_app.config['ARTIFACT_DIR'])
    artifact_path = artifact_dir / f'{experiment_id}_artifacts.h5'
    return artifact_path
