import datetime

from flask_login import UserMixin

from src.server.database.database import db


class LabelingJob(db.Model):
    """A labeling job"""
    job_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    date = db.Column(db.DateTime, default=datetime.datetime.utcnow)


class JobRegion(db.Model):
    """A region of the field of view"""
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    job_id = db.Column(db.Integer, db.ForeignKey(LabelingJob.job_id))
    experiment_id = db.Column(db.String, nullable=False)

    # Upper left of the region in the field of view coordinates
    x = db.Column(db.Integer, nullable=False)
    y = db.Column(db.Integer, nullable=False)

    # Width and height of the region
    width = db.Column(db.Integer, nullable=False)
    height = db.Column(db.Integer, nullable=False)

    def __repr__(self):
        return f'id: {self.id}, job_id: {self.job_id}, experiment_id: ' \
               f'{self.experiment_id}, x: {self.x}, y: {self.y}, width: ' \
               f'{self.width}, height: {self.height}'


class User(UserMixin, db.Model):
    """A user"""
    id = db.Column(db.String, primary_key=True)


class UserCells(db.Model):
    """All ROIs within a region a user has labeled as cell"""
    user_id = db.Column(db.String, db.ForeignKey(User.id), primary_key=True)
    region_id = db.Column(db.Integer, db.ForeignKey(JobRegion.id),
                          primary_key=True)

    # json representation
    cells = db.Column(db.String, primary_key=True)


class UserRoi(db.Model):
    """Additional metadata a user has given for an ROI"""
    user_id = db.Column(db.String, db.ForeignKey(User.id), primary_key=True)
    region_id = db.Column(db.Integer, db.ForeignKey(JobRegion.id),
                          primary_key=True)
    roi_id = db.Column(db.Integer, primary_key=True)
    notes = db.Column(db.String)
