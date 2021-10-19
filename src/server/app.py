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
from flask import Flask, request, make_response, send_file
from ophys_etl.modules.segmentation.qc_utils.video_utils import \
    video_bounds_from_ROI, ThumbnailVideo

from util import convert_pil_image_to_base64

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

    artifact_dir = Path('/allen/aibs/informatics/danielsf'
                    '/classifier_prototype_data')
    artifact_path = artifact_dir / f'{experiment_id}_classifier_artifacts.h5'
    with h5py.File(artifact_path, 'r') as f:
        rois = json.loads((f['rois'][()]))
        roi_color_map = json.loads(f['roi_color_map'][()])

    all_contours = []

    for roi in rois:
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
        contours = contours[0].reshape(contours[0].shape[0], 2).tolist() if \
            len(contours) == 1 else []
        color = (255, 0, 0) if id == current_roi_id else roi_color_map[str(id)]
        all_contours.append({
            'contour': contours,
            'color': color,
            'id': id
        })
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
    img_str = convert_pil_image_to_base64(img=image)

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

    fov_row_min, fov_row_max = fov_bounds['y'][1], fov_bounds['y'][0]
    fov_col_min, fov_col_max = fov_bounds['x']

    mov = mov[start:end, fov_row_min:fov_row_max, fov_col_min:fov_col_max]
    # img_strs = []
    # for frame in mov:
    #     img = Image.fromarray(frame)
    #     img_str = convert_pil_image_to_base64(img=img)
    #     img_strs.append(img_str)
    #
    # data = {
    #     'frames': img_strs
    # }
    #
    # return data

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
