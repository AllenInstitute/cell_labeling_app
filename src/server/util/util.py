import base64
from io import BytesIO
from pathlib import Path
from typing import Dict, Tuple, Optional, List

import cv2
import matplotlib.cm
import numpy as np
import pandas as pd
from PIL import Image
from flask import current_app

from server.database.schemas import JobRegion

from src.server.artifact import ArtifactFile


def _is_roi_within_region(roi: Dict, region: JobRegion,
                          field_of_view_dimension=(512, 512),
                          include_overlapping_rois=True):
    """Returns whether an roi is within a region. An ROI is considered
    within a region if the mask intersects with the region
    :param roi:
        Is this ROI within region
    :param region:
        The region
    :param field_of_view_dimension:
        Field of view dimensions
    :param include_overlapping_rois:
        Whether to include ROIs that overlap with region but don't fit
        entirely within region
    :return:
        True if ROI is within region else False
    """
    region_mask = np.zeros(field_of_view_dimension, dtype='uint8')
    region_mask[region.x:region.x+region.width,
                region.y:region.y+region.height] = 1

    roi_mask = np.zeros(field_of_view_dimension, dtype='uint8')
    roi_mask[roi['y']:roi['y']+roi['height'],
             roi['x']:roi['x']+roi['width']] = roi['mask']

    intersection = roi_mask * region_mask

    if include_overlapping_rois:
        is_within = intersection.sum() > 1
    else:
        is_within = (intersection == roi_mask).all()
    return is_within


def _get_classifier_score_for_roi(roi_id: int, experiment_id: str):
    """
    Gets classifier probability of cell for ROI
    :param roi_id:
    :param experiment_id:
    :return:
        Classifier probability of cell for ROI
    """
    predictions = pd.read_csv(Path(current_app.config['PREDICTIONS_DIR']) /
                              f'{experiment_id}_inference.csv',
                              dtype={'experiment_id': str})
    predictions = predictions[predictions['experiment_id'] == experiment_id]
    predictions = predictions.set_index('roi-id')

    classifier_score = predictions.loc[roi_id]['y_score']
    return classifier_score


def get_soft_filter_roi_color(classifier_score: float,
                              color_map='viridis') -> Tuple[int, int,
                                                                 int]:
    """Gets color based on classifier score for a given ROI in order to draw
    attention to ROIs the classifier thinks are cells. Uses color map
    defined by color_map"""
    cmap = matplotlib.cm.get_cmap(color_map)

    color = tuple([int(255 * x) for x in cmap(classifier_score)][:-1])
    color = (color[0], color[1], color[2])
    return color


def get_rois_in_region(region: JobRegion,
                       include_overlapping_rois=True):
    """Gets all ROIs within a given region of the field of view.
    :param experiment_id:
        experiment id
    :param region:
        region to get contours for
    :param include_overlapping_rois:
        Whether to include ROIs that overlap with region but don't fit
        entirely within region
    :return:
        dict with keys
            - mask: boolean array of size width x height
            - x: upper left x coordinate of roi bounding box
            - y: upper left y coordinate of roi bounding box
            - width: roi bounding box width
            - height: roi bounding box height
            - id: roi id
            - classifier_score: classifier score
    """
    artifact_path = get_artifacts_path(experiment_id=region.experiment_id)
    af = ArtifactFile(path=artifact_path)
    rois = af.rois

    res = []
    for roi in rois:
        if not _is_roi_within_region(
                roi=roi, region=region,
                include_overlapping_rois=include_overlapping_rois):
            continue

        mask = roi['mask']
        x = roi['x']
        y = roi['y']
        width = roi['width']
        height = roi['height']
        id = roi['id']
        classifier_score = _get_classifier_score_for_roi(
            roi_id=id, experiment_id=region.experiment_id)

        res.append({
            'mask': mask,
            'x': x,
            'y': y,
            'width': width,
            'height': height,
            'id': id,
            'classifier_score': classifier_score
        })
    return res


def convert_pil_image_to_base64(img: Image) -> str:
    buffered = BytesIO()
    img.save(buffered, format="png")
    img_str = base64.b64encode(buffered.getvalue())
    img_str = f'data:image/png;base64,{img_str.decode()}'
    return img_str


def get_roi_contours_in_region(experiment_id: str, region: JobRegion,
                               include_overlapping_rois=True,
                               reshape_contours_to_list=True):
    """Gets all ROI contours within a given region of the field of view.
    :param experiment_id:
        experiment id
    :param region:
        region to get contours for
    :param include_overlapping_rois:
        Whether to include ROIs that overlap with region but don't fit
        entirely within region
    :param reshape_contours_to_list:
    :return:
        dict with keys
            - contours: list of contour x, y coordinates
            - color: color of contour
            - id: roi id
            - experiment_id: experiment id
            - classifier_score: classifier probability of cell,
            - box_x: upper-left bounding box x coordinate of contour,
            - box_y: upper-left bounding box y coordinate of contour,
            - box_width: bounding box width of contour,
            - box_height: bounding box height of contour,
    """
    all_contours = []

    rois = get_rois_in_region(
        region=region, include_overlapping_rois=include_overlapping_rois)

    for roi in rois:
        x = roi['x']
        y = roi['y']
        width = roi['width']
        height = roi['height']
        mask = roi['mask']
        id = roi['id']
        classifier_score = roi['classifier_score']

        blank = np.zeros((512, 512), dtype='uint8')
        blank[y:y + height, x:x + width] = mask
        contours, _ = cv2.findContours(blank, cv2.RETR_EXTERNAL,
                                       cv2.CHAIN_APPROX_NONE)
        if reshape_contours_to_list:
            contours = [
                contour.reshape(contour.shape[0], 2).tolist()
                for contour in contours
            ]

        color = get_soft_filter_roi_color(
            classifier_score=roi['classifier_score'])
        all_contours.append({
            'contours': contours,
            'color': color,
            'id': id,
            'classifier_score': classifier_score,
            'box_x': x,
            'box_y': y,
            'box_width': width,
            'box_height': height,
            'experiment_id': experiment_id
        })
    return all_contours


def get_trace(experiment_id: str, roi_id: str, point: Optional[List] = None):
    artifact_path = get_artifacts_path(experiment_id=experiment_id)
    af = ArtifactFile(path=artifact_path)

    if point is None:
        # retrieve precomputed trace
        trace = af.get_trace(roi_id=roi_id)
    else:
        # Pull the trace from the video for the point
        trace = af.get_trace(point=point)
    return trace


def get_artifacts_path(experiment_id: str):
    artifact_dir = Path(current_app.config['ARTIFACT_DIR'])
    artifact_path = artifact_dir / f'{experiment_id}_artifacts.h5'
    return artifact_path
