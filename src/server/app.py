import datetime
import json
import random
import time
from operator import concat
from pathlib import Path
from typing import Tuple, Dict, Optional

import h5py
import numpy as np
from PIL import Image
from evaldb.reader import EvalDBReader
from flask import Flask, request, send_file
from flask_sqlalchemy import SQLAlchemy
from ophys_etl.modules.segmentation.qc_utils.video_generator import (
    VideoGenerator)
from ophys_etl.modules.segmentation.qc_utils.video_utils import \
    video_bounds_from_ROI
from sqlalchemy import desc, and_, or_, text
from sqlalchemy.sql import functions

import util

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = \
    'sqlite:////allen/aibs/informatics/aamster/cell_labeling_app.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

ARTIFACT_DB = EvalDBReader(
    path=Path("/allen/aibs/informatics/segmentation_eval_dbs"
              "/ssf_mouse_id_409828.db"))


def get_random_roi_from_experiment() -> Tuple[Optional[str], Optional[Dict]]:
    user_has_labeled = db.session\
        .query(JobRois.experiment_id.concat('_').concat(JobRois.roi_id))\
        .join(UserLabel, UserLabel.job_roi_id == JobRois.id)\
        .filter(JobRois.job_id == JOB_ID, UserLabel.user_id == USER_ID).all()

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

    artifact_dir = Path('/allen/aibs/informatics/danielsf'
                    '/classifier_prototype_data')
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

    return experiment_id, roi


@app.route('/get_roi_contours')
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


@app.route("/get_random_roi")
def get_random_roi():
    experiment_id, roi = get_random_roi_from_experiment()
    return {
        'experiment_id': experiment_id,
        'roi': roi
    }


@app.route('/get_projection')
def get_projection():
    projection_type = request.args['type']
    experiment_id = request.args['experiment_id']
    experiment_id = int(experiment_id)

    projections = ARTIFACT_DB.get_backgrounds(
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


@app.route('/get_trace')
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


@app.route('/get_video', methods=['POST'])
def get_video():
    s = time.time()
    request_data = request.get_json(force=True)
    experiment_id = request_data['experiment_id']
    roi_id = int(request_data['roi_id'])
    include_current_roi_mask = request_data['include_current_roi_mask']
    include_all_roi_masks = request_data['include_all_roi_masks']
    padding = int(request_data.get('padding', 32))
    start, end = request_data['timeframe']

    artifact_dir = Path('/allen/aibs/informatics/danielsf'
                        '/classifier_prototype_data')
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


@app.route('/get_default_video_timeframe')
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


@app.route('/get_fov_bounds', methods=['POST'])
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


@app.route('/add_label', methods=['POST'])
def add_label():
    data = request.get_json(force=True)
    roi_id = db.session.query(JobRois.id).filter(
        JobRois.experiment_id == data['experiment_id'],
        JobRois.roi_id == int(data['roi_id']))\
        .first()
    roi_id = roi_id[0]
    user_label = UserLabel(user_id=USER_ID, job_roi_id=roi_id,
                           label=data['label'])
    db.session.add(user_label)
    db.session.commit()

    return 'success'


@app.after_request
def after_request(response):
    header = response.headers
    header['Access-Control-Allow-Origin'] = '*'
    return response


###################
# Database schemas
###################


class LabelingJob(db.Model):
    job_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    date = db.Column(db.DateTime, default=datetime.datetime.utcnow)


class JobRois(db.Model):
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    job_id = db.Column(db.Integer, db.ForeignKey(LabelingJob.job_id))
    experiment_id = db.Column(db.String, nullable=False)
    roi_id = db.Column(db.Integer, nullable=False)

    def __repr__(self):
        return f'id: {self.id}, job_id: {self.job_id}, experiment_id: ' \
               f'{self.experiment_id}, roi_id: {self.roi_id}'


class User(db.Model):
    user_id = db.Column(db.String, primary_key=True)


class UserLabel(db.Model):
    user_id = db.Column(db.String, db.ForeignKey(User.user_id),
                        primary_key=True)
    job_roi_id = db.Column(db.Integer, db.ForeignKey(JobRois.id),
                           primary_key=True)
    label = db.Column(db.String, nullable=False)


def _validate_user(user_id: str):
    all_users = db.session.query(User.user_id).all()
    all_user_ids = [x.user_id for x in all_users]
    if user_id not in all_user_ids:
        raise RuntimeError(f'Bad user id. Please choose one of these user '
                           f'ids: {all_user_ids}')


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('--user_id', required=True)

    args = parser.parse_args()

    _validate_user(user_id=args.user_id)

    # Set job id as current job id
    JOB_ID = db.session.query(LabelingJob.job_id).order_by(desc(
        LabelingJob.date)).scalar()

    # Note that this is hacky and should be stored in a session instead of
    # being given from command line. Doing this for simplicity.
    USER_ID = args.user_id

    app.run(debug=False)
