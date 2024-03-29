import json
from io import BytesIO

import numpy as np
from PIL import Image
from flask import render_template, request, send_file, Blueprint, \
    current_app
from flask_login import current_user, login_required
from ophys_etl.modules.roi_cell_classifier.video_utils import (
    get_thumbnail_video_from_artifact_file)

from cell_labeling_app.database.database import db
from cell_labeling_app.database.schemas import JobRegion, \
    UserLabels, UserRoiExtra, LabelingJob
from cell_labeling_app.util import util
from cell_labeling_app.util.util import get_artifacts_path, \
    get_user_has_labeled, get_completed_regions, \
    get_total_regions_in_labeling_job, create_roi_from_contours
from cell_labeling_app.imaging_plane_artifacts import ArtifactFile
from cell_labeling_app.util.util import get_next_region

api = Blueprint(name='api', import_name=__name__)


@api.route('/')
def index():
    if current_user.is_authenticated:
        return render_template(
            'index.html',
            port=current_app.config['PORT'],
            server_address=current_app.config['server_address']
        )
    else:
        return render_template(
            'login.html',
            port=current_app.config['PORT'],
            server_address=current_app.config['server_address']
        )


@api.route('/done.html')
@login_required
def done():
    return render_template('done.html')


@api.route('/get_roi_contours')
@login_required
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
@login_required
def get_random_region():
    job_id = int(request.args['job_id'])
    next_region = get_next_region(job_id=job_id)
    if not next_region:
        # No more to label
        return {
            'experiment_id': None,
            'region': None
        }

    region = next_region.to_dict()
    return {
        'experiment_id': next_region.experiment_id,
        'region': region
    }


@api.route('/get_projection')
@login_required
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


@api.route('/get_trace', methods=['POST'])
@login_required
def get_trace():
    request_data = request.get_json(force=True)
    trace = util.get_trace(
        experiment_id=request_data['experiment_id'],
        roi_id=request_data['roi']['id'],
        contours=request_data['roi']['contours'],
        is_user_added=request_data['roi']['isUserAdded'])

    # Trace seems to decrease to 0 at the end which makes visualization worse
    # Trim to last nonzero index
    nonzero = trace.nonzero()[0]
    if len(nonzero) > 0:
        trace = trace[:nonzero[-1]]

    trace = trace.tolist()
    return {
        'trace': trace
    }


@api.route('/get_motion_border')
@login_required
def get_motion_border():
    experiment_id = request.args['experiment_id']
    artifact_path = get_artifacts_path(experiment_id=experiment_id)
    af = ArtifactFile(path=artifact_path)
    mb = af.motion_border
    return {
        'left_side': mb.left_side,
        'right_side': mb.right_side,
        'top': mb.top,
        'bottom': mb.bottom
    }


@api.route('/get_video', methods=['POST'])
@login_required
def get_video():
    request_data = request.get_json(force=True)
    experiment_id = request_data['experiment_id']
    is_user_added = request_data['is_user_added']
    color = request_data['color']
    roi_id = request_data['roi_id']
    contours = request_data['contours']

    region_id = int(request_data['region_id'])

    include_current_roi_mask = request_data['include_current_roi_mask']
    include_all_roi_masks = request_data['include_all_roi_masks']
    padding = int(request_data.get('padding', 32))
    start, end = request_data['timeframe']

    artifact_path = get_artifacts_path(experiment_id=experiment_id)

    region = (db.session.query(JobRegion)
              .filter(JobRegion.id == region_id)
              .first())
    rois = util.get_rois_in_region(region=region)
    roi_color_map = {
        roi['id']: util.get_soft_filter_roi_color(
            classifier_score=roi['classifier_score']) for roi in rois}
    if is_user_added:
        roi = create_roi_from_contours(contours=contours)
        roi['id'] = roi_id

        # Add the user-drawn roi to the list of rois
        rois.append(roi)

        # Add a color
        roi_color_map[roi_id] = color

    this_roi = [x for x in rois if x['id'] == roi_id][0]

    timesteps = np.arange(start, end)

    if not include_current_roi_mask:
        roi_color_map = None

    roi_list = rois if include_all_roi_masks else None

    video = get_thumbnail_video_from_artifact_file(
        artifact_path=artifact_path,
        roi=this_roi,
        padding=padding,
        quality=9,
        timesteps=timesteps,
        fps=31,
        other_roi=roi_list,
        roi_color=roi_color_map)
    return send_file(path_or_file=video.video_path)


@api.route('/get_default_video_timeframe', methods=['POST'])
@login_required
def get_default_video_timeframe():
    request_data = request.get_json(force=True)
    trace = util.get_trace(
        experiment_id=request_data['experiment_id'],
        roi_id=request_data['roi']['id'],
        contours=request_data['roi']['contours'],
        is_user_added=request_data['roi']['isUserAdded'])

    max_idx = trace.argmax()
    start = float(max_idx - 300)
    end = float(max_idx + 300)
    return {
        'timeframe': (start, end)
    }


@api.route('/get_fov_bounds', methods=['POST'])
@login_required
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

    if len(contours) == 0:
        x_min, x_max = region.x, region.x + region.width
        y_min, y_max = region.y, region.y + region.height
    else:
        x = np.array([x['box_x'] for x in contours])
        y = np.array([x['box_y'] for x in contours])

        widths = np.array([x['box_width'] for x in contours])
        heights = np.array([x['box_height'] for x in contours])

        x_min, x_max = x.min(), (x + widths).max()
        y_min, y_max = y.min(), (y + heights).max()

    # Find the larger box, either the region box or the box containing all ROIs
    # that are contained within or overlap within the box
    # The box containing all ROIs will be smaller in the case there are few
    # ROIs within the region, and they are close together.
    # This ensures that we always return at least the region box
    # Region x is row and region y and col
    x_range = [
        min(float(x_min), region.y),
        max(float(x_max), region.y + region.width)
    ]

    y_range = [
        # Reversing because origin of plot is top-left instead of bottom-left
        max(float(y_max), region.x + region.height),
        min(float(y_min), region.x)
    ]

    return {
        'x': x_range,
        'y': y_range
    }


@api.route('/get_field_of_view_dimensions')
@login_required
def get_field_of_view_dimensions():
    dims = current_app.config['FIELD_OF_VIEW_DIMENSIONS']
    return {
        'field_of_view_dimensions': dims
    }


@api.route('/submit_region', methods=['POST'])
@login_required
def submit_region():
    """Inserts records for labels and additional user-submitted roi metadata"""
    data = request.get_json(force=True)
    user_id = current_user.get_id()

    # add labels
    user_labels = UserLabels(user_id=user_id, region_id=data['region_id'],
                             labels=json.dumps(data['labels']),
                             duration=data['duration'])
    db.session.add(user_labels)

    # add roi extra
    for roi in data['roi_extra']:
        roi_extra = UserRoiExtra(user_id=user_id, region_id=data['region_id'],
                                 roi_id=roi['roi_id'], notes=roi['notes'])
        db.session.add(roi_extra)

    db.session.commit()

    return 'success'


@api.route('/find_roi_at_coordinates', methods=['POST'])
@login_required
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

    # Add user-added rois to list of rois
    for roi in data['user_added_rois']:
        roi_id = roi['id']
        roi = create_roi_from_contours(contours=roi['contours'])
        roi['id'] = roi_id
        rois.append(roi)
        rois_in_region.append(roi_id)

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


@api.route('/get_label_stats', methods=['GET'])
@login_required
def get_label_stats():
    """
    Gets stats on user label counts, and num. remaining
    :return:
        Dict of stats
    """
    job_id = int(request.args['job_id'])
    user_has_labeled = get_user_has_labeled(job_id=job_id)
    completed = get_completed_regions(job_id=job_id)
    completed_by_others = get_completed_regions(job_id=job_id,
                                                exclude_current_user=True)
    total = get_total_regions_in_labeling_job(job_id=job_id)

    return {
        'n_user_has_labeled': len(user_has_labeled),
        'n_total': total,
        'n_completed': len(completed),
        'n_completed_by_others': len(completed_by_others),
        'num_labelers_required_per_region':
            current_app.config['LABELERS_REQUIRED_PER_REGION']
    }


@api.after_request
def after_request(response):
    header = response.headers
    header['Access-Control-Allow-Origin'] = '*'
    return response


@api.route('/get_user_submitted_labels')
@login_required
def get_user_submitted_labels():
    job_id = int(request.args['job_id'])
    labels = get_user_has_labeled(job_id=job_id)
    labels = [
        {
            'submitted': r['submitted'],
            'experiment_id': r['experiment_id'],
            'region_id': r['region_id']
        } for r in labels]
    return {
        'labels': labels
    }


@api.route('/get_region', methods=['GET'])
@login_required
def get_region():
    region_id = request.args['region_id']
    region_id = int(region_id)
    try:
        region = util.get_region(region_id=region_id)
        region = region.to_dict()
        return {
            'experiment_id': region['experiment_id'],
            'region': region
        }
    except RuntimeError as e:
        return e, 400


@api.route('/get_labels_for_region', methods=['GET'])
@login_required
def get_labels_for_region():
    region_id = request.args['region_id']
    region_id = int(region_id)
    labels, roi_extra = util.get_labels_for_region(region_id=region_id)
    return {
        'labels': labels,
        'roi_extra': roi_extra
    }


@api.route('/get_all_labels', methods=['GET'])
def get_all_labels():
    labels = util.get_all_labels()
    return labels.to_dict(orient='records')


@api.route('/update_labels_for_region', methods=['POST'])
@login_required
def update_labels_for_region():
    data = request.get_json(force=True)
    util.update_labels_for_region(region_id=data['region_id'],
                                  labels=data['labels'])
    util.update_roi_extra_for_region(region_id=data['region_id'],
                                     roi_extra=data['roi_extra'])
    return 'success'


@api.route('/get_all_labeling_jobs', methods=['GET'])
@login_required
def get_all_labeling_jobs():
    jobs = (db.session.query(LabelingJob).all())
    jobs = [
        {
            'name': j.name,
            'id': j.job_id
        } for j in jobs
    ]

    return {
        'jobs': jobs
    }
