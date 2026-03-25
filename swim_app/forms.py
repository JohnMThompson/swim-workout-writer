from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileRequired
from wtforms import (
    BooleanField,
    HiddenField,
    PasswordField,
    SelectField,
    StringField,
    SubmitField,
    TextAreaField,
)
from wtforms.validators import DataRequired, Length


class LoginForm(FlaskForm):
    username = StringField("Username", validators=[DataRequired(), Length(max=120)])
    password = PasswordField("Password", validators=[DataRequired()])
    submit = SubmitField("Sign in")


class UploadForm(FlaskForm):
    screenshot = FileField("Screenshot", validators=[FileRequired()])
    submit = SubmitField("Extract workout")


class ReviewForm(FlaskForm):
    upload_id = HiddenField(validators=[DataRequired()])
    workout_date = StringField("Workout date", validators=[DataRequired()])
    start_time = StringField("Start time", validators=[DataRequired()])
    end_time = StringField("End time")
    duration = StringField("Duration (minutes)", validators=[DataRequired()])
    total_distance_yards = StringField("Total distance yards", validators=[DataRequired()])
    location = StringField("Location", validators=[DataRequired()])
    comments = TextAreaField("Comments")
    freestyle_distance = StringField("Freestyle distance")
    breaststroke_distance = StringField("Breaststroke distance")
    backstroke_distance = StringField("Backstroke distance")
    butterfly_distance = StringField("Butterfly distance")
    allow_stroke_mismatch = BooleanField("Allow stroke total mismatch")
    submit = SubmitField("Save workout")


class MappingForm(FlaskForm):
    source_label = HiddenField(validators=[DataRequired()])
    target_stroke = SelectField(
        "Map to stroke",
        choices=[
            ("freestyle", "Freestyle"),
            ("breaststroke", "Breaststroke"),
            ("backstroke", "Backstroke"),
            ("butterfly", "Butterfly"),
        ],
        validators=[DataRequired()],
    )
    submit = SubmitField("Save mapping")
