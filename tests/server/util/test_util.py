import json
import tempfile
from typing import Optional
from unittest.mock import patch, MagicMock

import pytest
from cell_labeling_app.database.database import db
from cell_labeling_app.database.populate_labeling_job import Region
from cell_labeling_app.database.schemas import UserLabels
from cell_labeling_app.database.schemas import User, LabelingJob, JobRegion
from flask import Flask
from sqlalchemy import desc

from cell_labeling_app.util.util import get_next_region


class TestGetNextRegion:
    @classmethod
    def setup_class(cls):
        cls.db_fp = tempfile.NamedTemporaryFile('w', suffix='.db')

    def _init_db(self, labels_per_region_limit: Optional[int] = None):
        db_fp = tempfile.NamedTemporaryFile('w', suffix='.db')

        app = Flask(__name__)
        app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_fp.name}'
        app.config['LABELS_PER_REGION_LIMIT'] = labels_per_region_limit
        db.init_app(app)
        with app.app_context():
            db.create_all()
        app.app_context().push()

        self.app = app

        self.db_fp = db_fp

        self.user_ids = list(range(4))
        self._populate_users()
        self._populate_labeling_job()

    def teardown(self):
        self.db_fp.close()

    def _populate_users(self):
        for user_id in self.user_ids:
            user = User(id=str(user_id))
            db.session.add(user)
            db.session.commit()

    @staticmethod
    def _populate_labeling_job():
        job = LabelingJob()
        db.session.add(job)

        job_id = db.session.query(LabelingJob.job_id).order_by(desc(
            LabelingJob.date)).first()[0]

        region = Region(
            x=0,
            y=0,
            experiment_id='0',
            width=10,
            height=10
        )
        job_region = JobRegion(job_id=job_id,
                               experiment_id=region.experiment_id,
                               x=region.x, y=region.y, width=region.width,
                               height=region.height)
        db.session.add(job_region)
        db.session.commit()

    @pytest.mark.parametrize('labels_per_region_limit', (None, 3))
    def test_get_next_region(self, labels_per_region_limit):
        """Tests that if labels_per_region_limit, then when enough labels
        have been given for a single region, that it is not sampled. If no
        limit, then sampling it again is fine"""
        self._init_db(labels_per_region_limit=labels_per_region_limit)
        user_ids = self.user_ids[:-1]

        # ALl users but last give a label for the same region
        # (there is only 1 region)
        for user_id in user_ids:
            user_labels = UserLabels(user_id=str(user_id), region_id=1,
                                     labels=json.dumps({}))
            db.session.add(user_labels)
        db.session.commit()

        # The last user tries to get a region. If labels_per_region_limit,
        # then this user should not be able to sample the region
        with patch('cell_labeling_app.util.util.current_user') as mock_user:
            mock_user.get_id = MagicMock(return_value='3')
            next_region = get_next_region()

        if labels_per_region_limit is not None:
            assert next_region is None
        else:
            assert next_region.id == 1


