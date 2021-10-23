import json
import random
from pathlib import Path

import h5py
import numpy as np
from PIL import Image
from evaldb.reader import EvalDBReader
from flask import render_template, request, send_file, Blueprint, current_app
from ophys_etl.modules.segmentation.qc_utils.video_generator import \
    VideoGenerator
from ophys_etl.modules.segmentation.qc_utils.video_utils import \
    video_bounds_from_ROI
from sqlalchemy import desc

from src.server.database.database import db
from src.server.database.schemas import JobRois, UserLabel, LabelingJob
from src.server.util import util

api = Blueprint(name='api', import_name=__name__)


def get_current_job_id() -> int:
    """
    Gets the current job id by finding the job most recently created
    :return:
        current job id
    """
    job_id = db.session.query(LabelingJob.job_id).order_by(desc(
        LabelingJob.date)).scalar()
    return job_id


@api.route('/')
def index():
    return render_template('index.html')


@api.route('/get_roi_contours')
def get_roi_contours():
    experiment_id = request.args.get('experiment_id')
    current_roi_id = request.args.get('current_roi_id')
    include_all_contours = request.args.get('include_all_contours') == 'true'

    all_contours = util.get_roi_contours(experiment_id=experiment_id,
                                         current_roi_id=current_roi_id,
                                         include_all_rois=include_all_contours)
    return {
        'contours': all_contours
    }


@api.route("/get_random_roi")
def get_random_roi():
    job_id = get_current_job_id()
    user_has_labeled = db.session\
        .query(JobRois.experiment_id.concat('_').concat(JobRois.roi_id))\
        .join(UserLabel, UserLabel.job_roi_id == JobRois.id)\
        .filter(JobRois.job_id == job_id, UserLabel.user_id ==
                'adam.amster').all()

    next_roi_candidates = db.session\
        .query(JobRois.experiment_id, JobRois.roi_id)

    for roi in user_has_labeled:
        roi = roi[0]
        next_roi_candidates = next_roi_candidates.filter(
            JobRois.experiment_id.concat('_').concat(JobRois.roi_id) != roi)

    next_roi_candidates = next_roi_candidates.all()

    if not next_roi_candidates:
        return None, None

    next_roi = random.choice(next_roi_candidates)

    experiment_id, roi_id = next_roi

    artifact_dir = Path(current_app.config['ARTIFACT_DIR'])
    artifact_path = artifact_dir / f'{experiment_id}_classifier_artifacts.h5'
    with h5py.File(artifact_path, 'r') as f:
        rois = json.loads((f['rois'][()]))

    roi = [x for x in rois if x['id'] == roi_id][0]

    roi = {
        'experiment_id': experiment_id,
        'id': roi['id'],
        'x': roi['x'],
        'y': roi['y'],
        'width': roi['width'],
        'height': roi['height']
    }
    return {
        'experiment_id': experiment_id,
        'roi': roi
    }


@api.route('/get_projection')
def get_projection():
    projection_type = request.args['type']
    experiment_id = request.args['experiment_id']
    experiment_id = int(experiment_id)

    artifact_db = EvalDBReader(current_app.config['ARTIFACT_DB_PATH'])
    projections = artifact_db.get_backgrounds(
        ophys_experiment_id=experiment_id)

    # TODO add background type to artifact DB
    if projection_type == 'max':
        path = [x for x in projections if 'max_proj' in x.stem][0]
    elif projection_type == 'average':
        path = [x for x in projections if 'avg_proj' in x.stem][0]
    elif projection_type == 'correlation':
        path = [x for x in projections if 'correlation_proj' in
                      x.stem][0]
    else:
        return 'bad projection type', 400

    image = Image.open(path)
    img_str = util.convert_pil_image_to_base64(img=image)

    return {
        'projection': img_str
    }


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

    artifact_dir = Path(current_app.config['ARTIFACT_DIR'])
    artifact_path = artifact_dir / f'{experiment_id}_classifier_artifacts.h5'

    with h5py.File(artifact_path, 'r') as f:
        video_generator = VideoGenerator(video_data=f['video_data'][()])
        rois = json.loads(f['rois'][()])
        roi_color_map = json.loads(f['roi_color_map'][()])
        roi_color_map = {int(roi_id): tuple(roi_color_map[roi_id])
                         for roi_id in roi_color_map}

    this_roi = rois[roi_id]
    timesteps = np.arange(start, end)

    roi_color_map[roi_id] = (255, 0, 0) if include_current_roi_mask else None
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
    roi = request.get_json(force=True)
    print(roi)

    (origin,
     frame_shape) = video_bounds_from_ROI(
        roi=roi,
        fov_shape=(512, 512),
        padding=32)

    origin = [float(x) for x in origin]
    frame_shape = [float(x) for x in frame_shape]

    x_range = [origin[1], origin[1] + frame_shape[1]]

    # Reversing because origin of plot is top-left instead of bottom-left
    y_range = [origin[0] + frame_shape[0], origin[0]]

    print(x_range)
    print(y_range)

    return {
        'x': x_range,
        'y': y_range
    }


@api.route('/add_label', methods=['POST'])
def add_label():
    data = request.get_json(force=True)
    roi_id = db.session.query(JobRois.id).filter(
        JobRois.experiment_id == data['experiment_id'],
        JobRois.roi_id == int(data['roi_id']))\
        .first()
    roi_id = roi_id[0]
    user_label = UserLabel(user_id='adam.amster', job_roi_id=roi_id,
                           label=data['label'])
    db.session.add(user_label)
    db.session.commit()

    return 'success'


@api.after_request
def after_request(response):
    header = response.headers
    header['Access-Control-Allow-Origin'] = '*'
    return response