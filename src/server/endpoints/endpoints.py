import json
import random
from io import BytesIO

import h5py
import numpy as np
from PIL import Image
from flask import render_template, request, send_file, Blueprint, current_app
from flask_login import current_user
from ophys_etl.modules.segmentation.qc_utils.video_generator import \
    VideoGenerator
from ophys_etl.modules.segmentation.qc_utils.video_utils import \
    video_bounds_from_ROI
from sqlalchemy import desc

from src.server.database.database import db
from src.server.database.schemas import LabelingJob, JobRegion, UserCells
from src.server.util import util
from src.server.util.util import get_artifacts_path

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
         .query(UserCells.region_id)
         .join(JobRegion, JobRegion.id == UserCells.region_id)
         .filter(JobRegion.job_id == job_id,
                 UserCells.user_id == current_user.get_id())
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

    with h5py.File(artifact_path, 'r') as f:
        if projection_type == 'max':
            dataset_name = 'max_projection'
        elif projection_type == 'average':
            dataset_name = 'avg_projection'
        elif projection_type == 'correlation':
            dataset_name = 'correlation_projection'
        else:
            return 'bad projection type', 400
        projection = f[dataset_name][:]

    if len(projection.shape) == 3:
        projection = projection[:, :, 0]
    projection = projection.astype('uint16')

    image = Image.fromarray(projection)
    image = image.tobytes()
    return send_file(
        BytesIO(image),
        mimetype='image/png')


@api.route('/get_trace')
def get_trace():
    experiment_id = request.args['experiment_id']
    roi_id = request.args['roi_id']

    trace = util.get_trace(experiment_id=experiment_id, roi_id=roi_id)

    # Trace seems to decrease to 0 at the end which makes visualization worse
    # Trim to last nonzero index
    trace = trace[:trace.nonzero()[0][-1]]

    trace = trace.tolist()
    return {
        'trace': trace
    }


@api.route('/get_video', methods=['POST'])
def get_video():
    request_data = request.get_json(force=True)
    experiment_id = request_data['experiment_id']
    roi_id = int(request_data['roi_id'])
    include_current_roi_mask = request_data['include_current_roi_mask']
    include_all_roi_masks = request_data['include_all_roi_masks']
    padding = int(request_data.get('padding', 32))
    start, end = request_data['timeframe']

    artifact_path = get_artifacts_path(experiment_id=experiment_id)

    with h5py.File(artifact_path, 'r') as f:
        video_generator = VideoGenerator(video_data=f['video_data'][()])
        rois = json.loads(f['rois'][()])
        roi_color_map = json.loads(f['roi_color_map'][()])
        roi_color_map = {int(roi_id): tuple(roi_color_map[roi_id])
                         for roi_id in roi_color_map}

    this_roi = rois[roi_id]
    timesteps = np.arange(start, end)

    if include_current_roi_mask:
        roi_color_map[roi_id] = (255, 0, 0)
    else:
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
    experiment_id = request.args['experiment_id']
    roi_id = request.args['roi_id']

    trace = util.get_trace(experiment_id=experiment_id, roi_id=roi_id)

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
              .filter(JobRegion.id == r['region']['id'])
              .first())

    contours = util.get_roi_contours_in_region(
        experiment_id=r['experiment_id'], region=region)

    x = np.array([x['box_x'] for x in contours])
    y = np.array([x['box_y'] for x in contours])

    return {
        'x': [float(x.min()), float(x.max())],
        'y': [float(y.min()), float(y.max())]
    }


@api.route('/add_label', methods=['POST'])
def add_label():
    data = request.get_json(force=True)
    job_id = db.session.query(LabelingJob.job_id).order_by(desc(
        LabelingJob.date)).first()[0]
    roi_id = db.session.query(JobRois.id).filter(
        JobRois.job_id == job_id,
        JobRois.experiment_id == data['experiment_id'],
        JobRois.roi_id == int(data['roi_id']))\
        .first()
    roi_id = roi_id[0]
    user_id = current_user.get_id()
    user_label = UserLabel(user_id=user_id, job_roi_id=roi_id,
                           label=data['label'], notes=data['notes'])
    db.session.add(user_label)
    db.session.commit()

    return 'success'


@api.after_request
def after_request(response):
    header = response.headers
    header['Access-Control-Allow-Origin'] = '*'
    return response