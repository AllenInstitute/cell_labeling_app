import json
import tempfile
from typing import Optional, List
from unittest.mock import patch, MagicMock

import pytest
from cell_labeling_app.database.database import db
from cell_labeling_app.database.populate_labeling_job import Region
from cell_labeling_app.database.schemas import UserLabels
from cell_labeling_app.database.schemas import User, LabelingJob, JobRegion
from flask import Flask
from sqlalchemy import desc

from cell_labeling_app.util.util import get_next_region, get_all_labels


class TestGetNextRegion:
    @classmethod
    def setup_class(cls):
        cls.db_fp = tempfile.NamedTemporaryFile('w', suffix='.db')

    def _init_db(self, labels_per_region_limit: Optional[int] = None,
                 num_regions=1):
        db_fp = tempfile.NamedTemporaryFile('w', suffix='.db')

        app = Flask(__name__)
        app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_fp.name}'
        app.config['LABELERS_REQUIRED_PER_REGION'] = labels_per_region_limit
        db.init_app(app)
        with app.app_context():
            db.create_all()
        app.app_context().push()

        self.app = app

        self.db_fp = db_fp

        self.user_ids = list(range(4))
        self._populate_users()
        self._populate_labeling_job(num_regions=num_regions)

    def teardown(self):
        self.db_fp.close()

    def _populate_users(self):
        for user_id in self.user_ids:
            user = User(id=str(user_id))
            db.session.add(user)
            db.session.commit()

    @staticmethod
    def _populate_labeling_job(num_regions=1):
        job = LabelingJob()
        db.session.add(job)

        job_id = db.session.query(LabelingJob.job_id).order_by(desc(
            LabelingJob.date)).first()[0]

        for _ in range(num_regions):
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
            next_region = get_next_region(job_id=1)

        if labels_per_region_limit is not None:
            assert next_region is None
        else:
            assert next_region.id == 1

    @pytest.mark.parametrize('prioritize_regions_by_label_count',
                             [True, False])
    # Dummy to repeat this 10 times in case we get lucky
    @pytest.mark.parametrize('_', range(10))
    def test_prioritize_regions_by_label_count(
            self, prioritize_regions_by_label_count, _):
        self._init_db(labels_per_region_limit=3, num_regions=3)

        # Region 1 gets 2 labels
        self._add_labels(user_ids=self.user_ids[:2], region_ids=[1])

        # Region 2 gets 1 label
        self._add_labels(user_ids=self.user_ids[:1], region_ids=[2])

        next_region = self._get_next_region(
            user_id='3',
            prioritize_regions_by_label_count=
            prioritize_regions_by_label_count)

        if prioritize_regions_by_label_count:
            # we expect the region with
            # more labels to be sampled
            assert next_region.id == 1
        else:
            # If not prioritize_almost_finished_regions,
            # any region can be sampled
            assert next_region.id in (1, 2, 3)

        # Region 2 gets another label
        self._add_labels(user_ids=[self.user_ids[2]], region_ids=[2])

        next_region = self._get_next_region(
            user_id='3',
            prioritize_regions_by_label_count=
            prioritize_regions_by_label_count)

        if prioritize_regions_by_label_count:
            # we expect the region with
            # more labels to be sampled (2 regions both have equal # labels)
            assert next_region.id in (1, 2)
        else:
            # If not prioritize_almost_finished_regions,
            # any region can be sampled
            assert next_region.id in (1, 2, 3)

        # Regions 1&2 gets another label
        self._add_labels(user_ids=[self.user_ids[3]], region_ids=[1, 2])

        next_region = self._get_next_region(
            user_id='3',
            prioritize_regions_by_label_count=
            prioritize_regions_by_label_count)

        # There's only 1 region left
        assert next_region.id == 3

    def test_get_all_labels(self):
        self._init_db(labels_per_region_limit=3, num_regions=3)
        self._add_labels(user_ids=self.user_ids[:2], region_ids=[1])
        self._add_labels(user_ids=self.user_ids[:1], region_ids=[2])

        labels = get_all_labels()
        assert labels.shape[0] > 0 and \
               set(labels.columns) == {'experiment_id', 'labels', 'user_id'}

    @staticmethod
    def _get_next_region(user_id: str,
                         prioritize_regions_by_label_count: bool) -> JobRegion:
        with patch('cell_labeling_app.util.util.current_user') as mock_user:
            mock_user.get_id = MagicMock(return_value=user_id)
            next_region = get_next_region(
                prioritize_regions_by_label_count=
                prioritize_regions_by_label_count,
                job_id=1
            )
            return next_region

    @staticmethod
    def _add_labels(user_ids: List[str], region_ids: List[int]):
        for user_id in user_ids:
            for region_id in region_ids:
                labels = [
                    {
                        'roi_id': 0,
                        'is_user_added': False,
                        'contours': None,
                        'label': 'cell'
                    }
                ]
                user_labels = UserLabels(user_id=str(user_id),
                                         region_id=region_id,
                                         labels=json.dumps(labels))
                db.session.add(user_labels)
        db.session.commit()
