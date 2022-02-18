import json
import random
from io import BytesIO
from typing import List

import cv2
import numpy as np
from PIL import Image
from flask import render_template, request, send_file, Blueprint, current_app, \
    Request
from flask_login import current_user
from ophys_etl.utils.thumbnail_video_generator import VideoGenerator
from sqlalchemy import desc

from server.database.database import db
from server.database.schemas import LabelingJob, JobRegion, UserLabels, \
    UserRoiExtra
from server.util import util
from server.util.util import get_artifacts_path

from src.server.artifact import ArtifactFile

api = Blueprint(name='api', import_name=__name__)


@api.route('/')
def index():
    if current_user.is_authenticated:
        return render_template('index.html', port=current_app.config['PORT'])
    else:
        return render_template('login.html', port=current_app.config['PORT'])


@api.route('/done.html')
def done():
    return render_template('done.html')


@api.route('/get_roi_contours')
def get_roi_contours():
    experiment_id = request.args['experiment_id']
    current_region_id = request.args['current_region_id']
    current_region_id = int(current_region_id)

    region = (db.session.query(JobRegion)
              .filter(JobRegion.id == current_region_id)
              .first())
    all_contours = util.get_roi_contours_in_region(experiment_id=experiment_id,
                                                   region=region)
    return {
        'contours': all_contours
    }


@api.route("/get_random_region")
def get_random_region():
    # job id is most recently created job id
    job_id = db.session.query(LabelingJob.job_id).order_by(desc(
        LabelingJob.date)).first()[0]

    # Get all region ids user has labeled
    user_has_labeled = \
        (db.session
         .query(UserLabels.region_id)
         .join(JobRegion, JobRegion.id == UserLabels.region_id)
         .filter(JobRegion.job_id == job_id,
                 UserLabels.user_id == current_user.get_id())
         .all())

    # Get initial next region candidates query
    next_region_candidates = \
        (db.session
         .query(JobRegion)
         .filter(JobRegion.job_id == job_id))

    # Add filter to next_region_candidates query so user does not label a
    # region that has already been labeled
    for region_id in user_has_labeled:
        region_id = region_id[0]
        next_region_candidates = next_region_candidates.filter(
            JobRegion.id != region_id)

    next_region_candidates = next_region_candidates.all()

    if not next_region_candidates:
        # No more to label
        return {
            'experiment_id': None,
            'region': None
        }

    next_region: JobRegion = random.choice(next_region_candidates)

    region = {
        'experiment_id': next_region.experiment_id,
        'id': next_region.id,
        'x': next_region.x,
        'y': next_region.y,
        'width': next_region.width,
        'height': next_region.height
    }
    return {
        'experiment_id': next_region.experiment_id,
        'region': region
    }


@api.route('/get_projection')
def get_projection():
    projection_type = request.args['type']
    experiment_id = request.args['experiment_id']

    artifact_path = get_artifacts_path(experiment_id=experiment_id)

    af = ArtifactFile(path=artifact_path)
    try:
        projection = af.get_projection(projection_type=projection_type)
    except ValueError as e:
        return e, 400

    image = Image.fromarray(projection)
    image = image.tobytes()
    return send_file(
        BytesIO(image),
        mimetype='image/png')


@api.route('/get_trace')
def get_trace():
    trace = _get_trace(request=request)

    # Trace seems to decrease to 0 at the end which makes visualization worse
    # Trim to last nonzero index
    nonzero = trace.nonzero()[0]
    if len(nonzero) > 0:
        trace = trace[:nonzero[-1]]

    trace = trace.tolist()
    return {
        'trace': trace
    }


@api.route('/get_video', methods=['POST'])
def get_video():
    request_data = request.get_json(force=True)
    experiment_id = request_data['experiment_id']
    is_segmented = request_data['is_segmented']
    color = request_data['color']
    roi_id = request_data['roi_id']

    if is_segmented:
        point = None
    else:
        # It's a non-segmented point
        point = request_data['point']
    region_id = int(request_data['region_id'])

    include_current_roi_mask = request_data['include_current_roi_mask']
    include_all_roi_masks = request_data['include_all_roi_masks']
    padding = int(request_data.get('padding', 32))
    start, end = request_data['timeframe']

    artifact_path = get_artifacts_path(experiment_id=experiment_id)

    af = ArtifactFile(path=artifact_path)
    video_generator = VideoGenerator(video_data=af.video)

    region = (db.session.query(JobRegion)
              .filter(JobRegion.id == region_id)
              .first())
    rois = util.get_rois_in_region(region=region)
    roi_color_map = {
        roi['id']: util.get_soft_filter_roi_color(
            classifier_score=roi['classifier_score']) for roi in rois}
    if not is_segmented:
        # Add the point to the list of rois
        radius = 4
        mask = _create_circle_mask_for_nonsegmented_point(
                point=point, radius=radius)
        rois.append({
            'id': roi_id,
            'x': point[0]-radius,
            'y': point[1]-radius,
            'width': len(mask[1]),
            'height': len(mask[0]),
            'mask': mask
        })
        # Add a color
        roi_color_map[roi_id] = color

    this_roi = [x for x in rois if x['id'] == roi_id][0]

    timesteps = np.arange(start, end)

    if not include_current_roi_mask:
        roi_color_map = None

    roi_list = rois if include_all_roi_masks else None

    video = video_generator.get_thumbnail_video_from_roi(
        this_roi,
        padding=padding,
        quality=9,
        timesteps=timesteps,
        fps=31,
        other_roi=roi_list,
        roi_color=roi_color_map)
    return send_file(path_or_file=video.video_path)


@api.route('/get_default_video_timeframe')
def get_default_video_timeframe():
    trace = _get_trace(request=request)

    max_idx = trace.argmax()
    start = float(max_idx - 300)
    end = float(max_idx + 300)
    return {
        'timeframe': (start, end)
    }


@api.route('/get_fov_bounds', methods=['POST'])
def get_fov_bounds():
    """The FOV bounds are the min/max x, y values of the bounding boxes to
    all ROIs that fit in the region. The reason why the region x, y, width,
    height was not just used is in the case of ROIs that don't fit within
    the region entirely. In that case, we need to expand the region
    dimensions so that all ROIs are in view. """
    r = request.get_json(force=True)

    region = (db.session.query(JobRegion)
              .filter(JobRegion.id == r['id'])
              .first())

    contours = util.get_roi_contours_in_region(
        experiment_id=r['experiment_id'], region=region)

    x = np.array([x['box_x'] for x in contours])
    y = np.array([x['box_y'] for x in contours])

    widths = np.array([x['box_width'] for x in contours])
    heights = np.array([x['box_height'] for x in contours])

    x_min, x_max = x.min(), (x + widths).max()
    y_min, y_max = y.min(), (y + heights).max()

    return {
        'x': [float(x_min), float(x_max)],

        # Reversing because origin of plot is top-left instead of bottom-left
        'y': [float(y_max), float(y_min)]
    }


@api.route('/submit_region', methods=['POST'])
def submit_region():
    """Inserts records for labels and additional user-submitted roi metadata"""
    data = request.get_json(force=True)
    user_id = current_user.get_id()

    # add labels
    user_labels = UserLabels(user_id=user_id, region_id=data['region_id'],
                             labels=json.dumps(data['labels']))
    db.session.add(user_labels)

    # add roi extra
    for roi in data['roi_extra']:
        roi_extra = UserRoiExtra(user_id=user_id, region_id=data['region_id'],
                                 roi_id=roi['roi_id'], notes=roi['notes'])
        db.session.add(roi_extra)

    db.session.commit()

    return 'success'


@api.route('/find_roi_at_coordinates', methods=['POST'])
def find_roi_at_coordinates():
    """
    Finds ROI id at field of view x, y coordinates
    from a set of candidate rois

    Request body
    -------------
    - current_region_id:
        Currently displayed region id
    - roi_ids
        All roi ids in the currently displayed region
    - coordinates
        x, y coordinates in field of view at which to find roi

    :return:
        json containing roi id at coordinates
    """
    data = request.get_json(force=True)

    current_region_id = data['current_region_id']
    rois_in_region = data['roi_ids']
    x, y = data['coordinates']

    region = (db.session.query(JobRegion)
              .filter(JobRegion.id == current_region_id)
              .first())

    artifact_path = get_artifacts_path(experiment_id=region.experiment_id)
    af = ArtifactFile(path=artifact_path)
    rois = af.rois

    # 1) First limit candidate rois to rois in region
    rois = [x for x in rois if x['id'] in rois_in_region]

    # 2) Then limit candidate rois to rois whose bounding boxes intersect
    # with coordinates
    rois = [roi for roi in rois if
            (roi['x'] <= x <= roi['x'] + roi['width']) and
            (roi['y'] <= y <= roi['y'] + roi['height'])]

    # 3) Detect in a greedy fashion which of the candidate ROIs has a point
    # at coordinates
    for roi in rois:
        roi_x = roi['x']
        roi_y = roi['y']
        roi_width = roi['width']
        roi_height = roi['height']

        roi_mask = np.zeros(current_app.config['FIELD_OF_VIEW_DIMENSIONS'],
                            dtype='uint8')
        roi_mask[roi_y:roi_y+roi_height, roi_x:roi_x+roi_width] = roi['mask']

        if roi_mask[y, x] == 1:
            return {
                'roi_id': roi['id']
            }

    return {
        'roi_id': None
    }


@api.after_request
def after_request(response):
    header = response.headers
    header['Access-Control-Allow-Origin'] = '*'
    return response


def _get_trace(request: Request) -> np.ndarray:
    """

    :param request: The flask request
    :return:
        trace, np.ndarray, or none if non-computed trace
        is requested """
    experiment_id = request.args['experiment_id']
    roi_id = request.args['roi_id']
    is_segmented = request.args['is_segmented'] == 'true'
    if is_segmented:
        point = None
    else:
        # It is a non-segmented point, rather than a segmented ROI
        point = [int(x) for x in roi_id.split(',')]
    trace = util.get_trace(experiment_id=experiment_id,
                           roi_id=roi_id, point=point)
    return trace


def _create_circle_mask_for_nonsegmented_point(
        point: List[int],
        radius=8,
        image_dims=(512, 512)):
    """
    Returns a circular mask that can be displayed on video for a point.
    :param point:
        Center location of circle
    :param radius:
        Radius of circle
    :param image_dims:
        Dimensions of image
    :return:
        Boolean mask as required by VideoGenerator for drawing contours
    """
    x = np.zeros(image_dims, dtype='uint8')
    x = cv2.circle(x, point, radius, [255, 255, 255])
    center_x, center_y = point
    return x[center_y - radius:center_y + radius+1,
             center_x - radius:center_x + radius+1].astype(bool).tolist()
