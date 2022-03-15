import datetime

from flask_login import UserMixin

from cell_labeling_app.database.database import db


class LabelingJob(db.Model):
    """A labeling job"""
    job_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    date = db.Column(db.DateTime, default=datetime.datetime.utcnow)


class JobRegion(db.Model):
    """A region of the field of view"""
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    job_id = db.Column(db.Integer, db.ForeignKey(LabelingJob.job_id))
    experiment_id = db.Column(db.String, nullable=False)

    x = db.Column(db.Integer, nullable=False,
                  doc='Row index in array coordinates of the region upper '
                      'left')
    y = db.Column(db.Integer, nullable=False,
                  doc='Column index in array coordinates of the region upper '
                      'left')

    # Width and height of the region
    width = db.Column(db.Integer, nullable=False)
    height = db.Column(db.Integer, nullable=False)

    def __repr__(self):
        return f'id: {self.id}, job_id: {self.job_id}, experiment_id: ' \
               f'{self.experiment_id}, x: {self.x}, y: {self.y}, width: ' \
               f'{self.width}, height: {self.height}'

    def to_dict(self) -> dict:
        region = {
            'experiment_id': self.experiment_id,
            'id': self.id,
            'x': self.x,
            'y': self.y,
            'width': self.width,
            'height': self.height
        }
        return region


class User(UserMixin, db.Model):
    """A user"""
    id = db.Column(db.String, primary_key=True)


class UserLabels(db.Model):
    """Labels for all ROIs within a region"""
    user_id = db.Column(db.String, db.ForeignKey(User.id), primary_key=True)
    region_id = db.Column(db.Integer, db.ForeignKey(JobRegion.id),
                          primary_key=True)

    # json representation
    labels = db.Column(db.String, primary_key=True)

    timestamp = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    duration = db.Column(db.Float, doc='The amount of time it took to label '
                                       'in seconds')


class UserRoiExtra(db.Model):
    """Additional metadata a user has given for an ROI"""
    user_id = db.Column(db.String, db.ForeignKey(User.id), primary_key=True)
    region_id = db.Column(db.Integer, db.ForeignKey(JobRegion.id),
                          primary_key=True)
    roi_id = db.Column(db.Integer, primary_key=True)
    notes = db.Column(db.String)
    timestamp = db.Column(db.DateTime, default=datetime.datetime.utcnow)
