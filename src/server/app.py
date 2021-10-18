import base64
import json
import os
import random
import re
from io import BytesIO
from pathlib import Path

import h5py
import numpy as np
from PIL import Image
from flask import Flask, request
from ophys_etl.modules.segmentation.qc_utils.video_utils import \
    video_bounds_from_ROI

app = Flask(__name__)


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
    projection_type = request.args.get('type')
    experiment_id = request.args.get('experiment_id')

    artifact_dir = Path('/allen/aibs/informatics/danielsf'
                    '/classifier_prototype_data')
    artifact_path = artifact_dir / f'{experiment_id}_classifier_artifacts.h5'

    if projection_type == 'max':
        with h5py.File(artifact_path, 'r') as f:
            projection = f['max_projection'][:]
    else:
        return 'bad projection type', 400

    projection = np.stack([projection, projection, projection], axis=-1)
    buffered = BytesIO()
    image = Image.fromarray(projection)
    image.save(buffered, format="png")
    img_str = base64.b64encode(buffered.getvalue())
    img_str = f'data:image/png;base64,{img_str.decode()}'

    return {
        'projection': img_str
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
    app.run(debug=True)