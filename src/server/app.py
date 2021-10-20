import gzip
import json
import os
import random
import re
import tempfile
import time
from pathlib import Path

import cv2
import h5py
import numpy as np
from PIL import Image
from evaldb.reader import EvalDBReader
from flask import Flask, request, send_file
from ophys_etl.modules.segmentation.qc_utils.video_utils import \
    video_bounds_from_ROI, ThumbnailVideo

import util

app = Flask(__name__)

ARTIFACT_DB = EvalDBReader(
    path=Path("/allen/aibs/informatics/segmentation_eval_dbs"
              "/ssf_mouse_id_409828.db"))


def get_random_experiment() -> str:
    artifact_dir = '/allen/aibs/informatics/danielsf/classifier_prototype_data'
    file_list = os.listdir(artifact_dir)
    exp_ids = [re.match('\d+', x).group() for x in file_list]
    exp_id = random.choice(exp_ids)
    return exp_id


def get_random_roi_from_experiment(experiment_id: str) -> dict:
    artifact_dir = Path('/allen/aibs/informatics/danielsf'
                    '/classifier_prototype_data')
    artifact_path = artifact_dir / f'{experiment_id}_classifier_artifacts.h5'
    with h5py.File(artifact_path, 'r') as f:
        rois = json.loads((f['rois'][()]))
    roi_idx = random.choice(range(len(rois)))

    return {
        'id': rois[roi_idx]['id'],
        'x': rois[roi_idx]['x'],
        'y': rois[roi_idx]['y'],
        'width': rois[roi_idx]['width'],
        'height': rois[roi_idx]['height']
    }


@app.route('/get_roi_contours')
def get_roi_contours():
    experiment_id = request.args.get('experiment_id')
    current_roi_id = request.args.get('current_roi_id')

    all_contours = util.get_roi_contours(experiment_id=experiment_id,
                                        current_roi_id=current_roi_id)
    return {
        'contours': all_contours
    }


@app.route("/get_random_roi")
def get_random_roi():
    exp_id = get_random_experiment()
    roi = get_random_roi_from_experiment(experiment_id=exp_id)
    return {
        'experiment_id': exp_id,
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

    artifact_dir = Path('/allen/aibs/informatics/danielsf'
                    '/classifier_prototype_data')
    artifact_path = artifact_dir / f'{experiment_id}_classifier_artifacts.h5'
    with h5py.File(artifact_path, 'r') as f:
        trace = (f['traces'][roi_id][()])

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
    roi_id = str(request_data['roi_id'])
    fov_bounds = request_data['fovBounds']
    include_current_roi_mask = request_data['include_current_roi_mask']
    include_all_roi_masks = request_data['include_all_roi_masks']
    timeframe = request_data.get('timeframe', None)

    artifact_dir = Path('/allen/aibs/informatics/danielsf'
                        '/classifier_prototype_data')
    artifact_path = artifact_dir / f'{experiment_id}_classifier_artifacts.h5'

    def get_default_timeframe_from_trace():
        with h5py.File(artifact_path, 'r') as f:
            trace = (f['traces'][roi_id][()])

        max_idx = trace.argmax()
        start = max_idx - 300
        end = max_idx + 300
        return start, end

    if not timeframe:
        start, end = get_default_timeframe_from_trace()
    else:
        start, end = timeframe

    with h5py.File(artifact_path, 'r') as f:
        mov = f['video_data'][:]

    if include_all_roi_masks or include_current_roi_mask:
        contours = util.get_roi_contours(
            experiment_id=experiment_id, current_roi_id=roi_id,
            include_all_rois=include_all_roi_masks,
            reshape_contours_to_list=False)

        # convert to 3 channels so that colored masks can be drawn on
        mov = np.stack([mov, mov, mov], axis=-1)

        for frame in mov:
            for contour in contours:
                cv2.drawContours(frame, contour['contour'],
                                 -1, contour['color'], 1)

    fov_row_min, fov_row_max = fov_bounds['y'][1], fov_bounds['y'][0]
    fov_col_min, fov_col_max = fov_bounds['x']

    mov = mov[start:end, fov_row_min:fov_row_max, fov_col_min:fov_col_max]

    with tempfile.NamedTemporaryFile(prefix='thumbnail_video_',
                                     suffix='.mp4') as f:

        _ = ThumbnailVideo(video_data=mov,
                                   video_path=Path(f.name),
                                   origin=None,
                                   timesteps=None,
                                   fps=31,
                                   quality=5)
        e = time.time()
        print(e - s)
        return send_file(path_or_file=f.name)



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


@app.after_request
def after_request(response):
    header = response.headers
    header['Access-Control-Allow-Origin'] = '*'
    return response


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('--debug', default=False, action='store_true')

    args = parser.parse_args()

    if args.debug:
        app.run(debug=True)
    else:
        from waitress import serve
        serve(app, port=5000)
