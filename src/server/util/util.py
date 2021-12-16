import base64
import json
from io import BytesIO
from pathlib import Path
from typing import Dict, Tuple

import cv2
import h5py
import matplotlib
import numpy as np
import pandas as pd
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


def _get_soft_filter_roi_color(roi_id: int, experiment_id: str,
                               color_map='viridis') -> Tuple[int, int, int]:
    """Gets color based on classifier score for a given ROI in order to draw
    attention to ROIs the classifier thinks are cells"""
    cmap = matplotlib.cm.get_cmap(color_map)
    predictions = pd.read_csv(Path(current_app.config['PREDICTIONS_DIR']) /
                              f'{experiment_id}_inference.csv',
                              dtype={'experiment_id': str})
    predictions = predictions[predictions['experiment_id'] == experiment_id]
    predictions = predictions.set_index('roi-id')

    classifier_score = predictions.loc[roi_id]['y_score']

    color = tuple([int(255 * x) for x in cmap(classifier_score)][:-1])
    color = (color[0], color[1], color[2])
    return color

def convert_pil_image_to_base64(img: Image) -> str:
    buffered = BytesIO()
    img.save(buffered, format="png")
    img_str = base64.b64encode(buffered.getvalue())
    img_str = f'data:image/png;base64,{img_str.decode()}'
    return img_str


def get_roi_contours(experiment_id: str, region: JobRegion,
                     reshape_contours_to_list=True,
                     color_map='viridis'):
    """Gets all ROIs within a given region of the field of view.
    :param experiment_id:
        experiment id
    :param region:
        region to get contours for
    :param color_map
        color map used for converting the classifier score into a color
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

        color = _get_soft_filter_roi_color(roi_id=id,
                                           experiment_id=experiment_id)
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
