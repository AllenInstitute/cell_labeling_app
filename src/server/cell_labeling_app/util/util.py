import base64
import json
import random
from io import BytesIO
from pathlib import Path
from typing import Dict, Tuple, Optional, List

import cv2
import matplotlib.cm
import numpy as np
import pandas as pd
from PIL import Image
from cell_labeling_app.database.database import db
from flask import current_app

from cell_labeling_app.database.schemas import JobRegion, UserLabels, \
    LabelingJob, UserRoiExtra
from cell_labeling_app.imaging_plane_artifacts import ArtifactFile
from flask_login import current_user
from sqlalchemy import func, desc


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
    region_mask[region.x:region.x+region.height,
                region.y:region.y+region.width] = 1

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
    predictions = pd.read_csv(
        Path(current_app.config['PREDICTIONS_DIR']) /
        f'{experiment_id}' / 'predictions' /
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
        contours, _ = cv2.findContours(blank, cv2.RETR_TREE,
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


def get_trace(
        experiment_id: str,
        roi_id: int,
        is_user_added: bool,
        contours: List[List[int]]
):
    """
    Gets a trace. If it is an already segmented object, pulls the precomputed
    trace. Otherwise, computes a trace.

    @param experiment_id: experiment id
    @param roi_id: roi id
    @param is_user_added: Whether the user added this ROI or it was precomputed
    @param contours: ROI contours, needed if is_user_added
    @return: trace
    """
    artifact_path = get_artifacts_path(experiment_id=experiment_id)
    af = ArtifactFile(path=artifact_path)

    roi = create_roi_from_contours(contours=contours)
    trace = af.get_trace(
        roi_id=roi_id,
        roi=roi,
        is_user_added=is_user_added)

    return trace


def get_artifacts_path(experiment_id: str):
    artifact_dir = Path(current_app.config['ARTIFACT_DIR'])
    artifact_path = artifact_dir / f'{experiment_id}_artifacts.h5'
    return artifact_path


def get_region_label_counts(
        exclude_current_user: bool = False,
        region_ids: Optional[List[int]] = None) -> pd.Series:
    """
    :param exclude_current_user: Exclude regions where current user
        contributed to completing it
    :param region_ids: Optional list of region ids to get counts for
    :return: Series with index region_id and values n_labelers
    """
    job_id = _get_current_job_id()
    region_label_counts = \
        (db.session
         .query(UserLabels.region_id,
                func.count())
         .join(JobRegion, JobRegion.id == UserLabels.region_id)
         .filter(JobRegion.job_id == job_id))
    if region_ids is not None:
        region_label_counts = \
            region_label_counts.filter(JobRegion.id.in_(region_ids))

    if exclude_current_user:
        region_label_counts = \
            (region_label_counts
             .filter(UserLabels.user_id != current_user.get_id()))
    region_label_counts = region_label_counts\
        .group_by(UserLabels.region_id)\
        .all()
    region_label_counts = pd.DataFrame.from_records(
        region_label_counts, columns=['region_id', 'n_labelers'])
    region_label_counts = (region_label_counts.set_index('region_id')
                           ['n_labelers'])

    # Need to add the regions with 0 labels
    unlabeled_regions = (
        db.session
        .query(JobRegion.id)
        .filter(~JobRegion.id.in_(region_label_counts.index.tolist()))
        .all()
    )
    unlabeled_regions = [x.id for x in unlabeled_regions]
    unlabeled_regions = pd.Series(0, index=unlabeled_regions)

    region_label_counts = pd.concat([region_label_counts, unlabeled_regions])

    return region_label_counts


def get_completed_regions(exclude_current_user: bool = False) -> List[int]:
    """
    This returns the regions with sufficient number of labels

    :param exclude_current_user: Exclude regions where current user
        contributed to completing it (returns regions completed by others)
    :rtype: list of completed region ids
    """
    region_label_counts = get_region_label_counts(
        exclude_current_user=exclude_current_user)
    regions_with_enough_labels = \
        region_label_counts.loc[
            region_label_counts >=
            current_app.config['LABELERS_REQUIRED_PER_REGION']]\
        .index.tolist()
    return regions_with_enough_labels


def get_user_has_labeled() -> List[Dict]:
    """
    Gets the list of region ids that the current user has labeled
    :return:
        List of dict with keys
            submitted: datetime label submitted
            region_id
            experiment_id
            x
    """
    job_id = _get_current_job_id()

    user_has_labeled = \
        (db.session
         .query(UserLabels.timestamp.label('submitted'),
                UserLabels.labels,
                JobRegion.id.label('region_id'),
                JobRegion.experiment_id)
         .join(JobRegion, JobRegion.id == UserLabels.region_id)
         .filter(JobRegion.job_id == job_id,
                 UserLabels.user_id == current_user.get_id())
         .order_by(UserLabels.timestamp.desc())
         .all())
    return user_has_labeled


def get_next_region(
        prioritize_regions_by_label_count: bool = True
) -> Optional[JobRegion]:
    """Samples a region randomly from a set of candidate regions.
    The candidate regions are those that have not already been labeled by the
    labeler and those that have not been labeled enough times by other
    labelers

    :param prioritize_regions_by_label_count: Whether to prioritize
        sampling regions that
        have been labeled more times. Encourages `LABELERS_REQUIRED_PER_REGION`
        to be met quicker for a given region
    :rtype: optional JobRegion
        JobRegion, if a candidate region exists, otherwise None
    """
    def get_regions_prioritized_by_num_labels(
            labelers_required_per_region: int,
            region_ids: List[int]
    ) -> List[int]:
        """

        :param labelers_required_per_region: Number of labelers required per
            region
        :param region_ids: The region ids to prioritize
        :return: region ids which have a label count closest to
            `labelers_required_per_region`
        """
        label_counts = get_region_label_counts(region_ids=region_ids)
        label_counts = label_counts[
            label_counts < labelers_required_per_region]
        label_counts = label_counts.sort_values(ascending=False)
        prioritized_regions = label_counts[
            label_counts == label_counts.max()].index.tolist()
        return prioritized_regions
    job_id = _get_current_job_id()

    # Get all region ids user has labeled
    user_has_labeled = get_user_has_labeled()
    user_has_labeled = [region['region_id'] for region in user_has_labeled]

    regions_with_enough_labels = get_completed_regions()
    exclude_regions = user_has_labeled + regions_with_enough_labels

    # Get initial next region candidates query
    next_region_candidates = \
        (db.session
         .query(JobRegion)
         .filter(JobRegion.job_id == job_id))

    # Add filter to next_region_candidates query so user does not label a
    # region that has already been labeled
    for region_id in exclude_regions:
        next_region_candidates = next_region_candidates.filter(
            JobRegion.id != region_id)

    next_region_candidates = next_region_candidates.all()
    next_region: Optional[JobRegion]

    if prioritize_regions_by_label_count and \
            current_app.config['LABELERS_REQUIRED_PER_REGION'] is not None:
        prioritized_regions = get_regions_prioritized_by_num_labels(
            labelers_required_per_region=
            current_app.config['LABELERS_REQUIRED_PER_REGION'],
            region_ids=[x.id for x in next_region_candidates]
        )
        prioritized_regions = set(prioritized_regions)
        next_region_candidates = [x for x in next_region_candidates
                                  if x.id in prioritized_regions]
    if not next_region_candidates:
        next_region = None
    else:
        next_region = random.choice(next_region_candidates)
    return next_region


def _get_current_job_id() -> int:
    """
    Gets the current job id, where current is the most recently made
    :return:
        job id
    """
    job_id = db.session.query(LabelingJob.job_id).order_by(desc(
        LabelingJob.date)).first()[0]
    return job_id


def get_total_regions_in_labeling_job() -> int:
    """
    Gets the total number of regions in the labeling job
    :return:
        total number of regions in labeling job
    """
    job_id = _get_current_job_id()
    n = (db.session
         .query(JobRegion)
         .filter(JobRegion.job_id == job_id)
         .count()
         )
    return n


def get_region(region_id: int) -> JobRegion:
    """
    Gets the region from the database given by `region_id`
    :param region_id:
        Region id
    :return:
        JobRegion for region_id
    """
    region = \
        (db.session
         .query(JobRegion)
         .filter(JobRegion.id == region_id)
         .first())
    return region


def get_labels_for_region(region_id: int) -> Tuple[List[dict], List[dict]]:
    """
    Gets the labels and roi meta for region given by `region_id`
    :param region_id:
        Region id
    :return:
        tuple of labels, roi_extra for region given by `region_id`
    """
    labels = \
        (db.session
         .query(UserLabels.labels)
         .filter(UserLabels.region_id == region_id)
         .filter(UserLabels.user_id == current_user.get_id())
         .first())
    labels = json.loads(labels[0])

    roi_extra = (
        db.session
        .query(UserRoiExtra)
        .filter(UserRoiExtra.user_id == current_user.get_id())
        .filter(UserRoiExtra.region_id == region_id)
        .all()
    )
    roi_extra = [{'roi_id': x.roi_id, 'notes': x.notes} for x in roi_extra]
    return labels, roi_extra


def get_all_labels() -> pd.DataFrame:
    """Gets all labels"""
    labels = (
        db.session.query(
            JobRegion.experiment_id,
            UserLabels.labels,
            UserLabels.user_id)
        .join(JobRegion,
              JobRegion.id == UserLabels.region_id)
        .all()
    )
    labels = pd.DataFrame(labels,
                          columns=['experiment_id', 'labels', 'user_id'])
    return labels


def update_labels_for_region(region_id: int, labels: List[dict]):
    """
    Updates labels for region given by `region_id`

    :param region_id:
        region id
    :param labels:
        labels
    :return: None
    """
    user_labels = (
        db.session
        .query(UserLabels)
        .filter(UserLabels.region_id == region_id)
        .filter(UserLabels.user_id == current_user.get_id())
        .first()
    )
    user_labels.labels = json.dumps(labels)
    db.session.commit()


def update_roi_extra_for_region(region_id: int, roi_extra: List[dict]):
    """
    Update roi extra for region. If not in db already, adds it.

    :param region_id:
        region id
    :param roi_extra:
        List of Dict with keys:
            - roi_id
            - notes
    :return: None
    """
    user_id = current_user.get_id()

    current_roi_extra = (
        db.session
        .query(UserRoiExtra.roi_id)
        .filter(UserRoiExtra.user_id == user_id)
        .filter(UserRoiExtra.region_id == region_id)
        .all()
    )
    current_roi_extra = set([x.roi_id for x in current_roi_extra])

    needs_update = [x for x in roi_extra if x['roi_id'] in current_roi_extra]
    needs_add = [x for x in roi_extra if x['roi_id'] not in current_roi_extra]

    for data in needs_update:
        roi_extra = (
            db.session
            .query(UserRoiExtra)
            .filter(UserRoiExtra.user_id == user_id)
            .filter(UserRoiExtra.region_id == region_id)
            .first()
        )
        roi_extra.notes = data['notes']
        db.session.commit()

    for data in needs_add:
        roi_extra = UserRoiExtra(user_id=user_id, region_id=region_id,
                                 roi_id=data['roi_id'], notes=data['notes'])
        db.session.add(roi_extra)

    db.session.commit()


def create_roi_from_contours(contours: List, image_dims=(512, 512)) -> Dict:
    """Given a list of points representing roi contours, create an ROI
    :param contours: list of roi contours
    :param image_dims: dimensions of FOV
    :return Dict
        x: upper left x coord of roi bounding box
        y: upper left y coord of roi bounding box
        width: width of roi bounding box
        height: height of roi bounding box
        mask: roi boolean mask within bounding box of size height x width
    """
    contours = np.array(contours, dtype=int)

    # 1. Get bounding box of contours

    contours_poly = cv2.approxPolyDP(
        # Only supporting single set of contours (i.e. not disconnected)
        contours[0],
        3,
        True
    )
    x1, y1, width, height = cv2.boundingRect(contours_poly)

    # 2. Get boolean mask within bounding box
    x = np.zeros(image_dims, dtype='uint8')

    # Create a mask for the set of contours
    cv2.drawContours(x, contours, -1, 1, -1)

    mask = x[y1:y1+height, x1:x1+width].astype(bool)

    return {
        'x': x1,
        'y': y1,
        'width': width,
        'height': height,
        'mask': mask
    }
