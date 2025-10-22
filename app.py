import os
import random
import uuid
from flask import Flask, render_template, request, redirect, url_for, flash, current_app
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import inspect, text
from sqlalchemy.orm import joinedload
from werkzeug.utils import secure_filename

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DATABASE_FILENAME = "quiz.db"


def _resolve_database_path() -> str:
    """Return the absolute path for the SQLite database file.

    The database must always live inside the dedicated ``data`` directory at the
    project root.  Any externally provided path is reduced to a filename so the
    database is still created inside that directory.
    """

    requested_path = os.getenv("DATABASE_PATH")
    if not requested_path:
        return os.path.join(DATA_DIR, DATABASE_FILENAME)

    # If an explicit path is provided, normalise it to a filename to ensure the
    # database is kept within the data directory regardless of configuration.
    filename = os.path.basename(requested_path)
    return os.path.join(DATA_DIR, filename or DATABASE_FILENAME)


DATABASE_PATH = _resolve_database_path()

def create_app():
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{DATABASE_PATH}'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'super-secret-key')
    app.config['UPLOAD_FOLDER'] = os.path.join(os.getcwd(), 'static', 'uploads')

    db.init_app(app)

    with app.app_context():
        os.makedirs(DATA_DIR, exist_ok=True)
        db.create_all()
        ensure_database_schema()
        ensure_default_records()

    register_routes(app)
    return app


db = SQLAlchemy()


class Question(db.Model):
    __tablename__ = 'questions'

    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.String(255), nullable=False)
    correct_answer = db.Column(db.String(255), nullable=False)
    image_path = db.Column(db.String(255))
    comment = db.Column(db.Text)
    secret_password = db.Column(db.String(128), nullable=False, default='')

    options = db.relationship('AnswerOption', backref='question', cascade='all, delete-orphan')


class AnswerOption(db.Model):
    __tablename__ = 'answer_options'

    id = db.Column(db.Integer, primary_key=True)
    question_id = db.Column(db.Integer, db.ForeignKey('questions.id'), nullable=False)
    text = db.Column(db.String(255), nullable=False)
    is_correct = db.Column(db.Boolean, default=False)


class QuizSettings(db.Model):
    __tablename__ = 'quiz_settings'

    id = db.Column(db.Integer, primary_key=True)
    final_message = db.Column(db.Text, default='')


class GameState(db.Model):
    __tablename__ = 'game_state'

    id = db.Column(db.Integer, primary_key=True)
    current_index = db.Column(db.Integer, default=0)


def ensure_database_schema() -> None:
    """Ensure legacy databases have the latest columns."""

    inspector = inspect(db.engine)
    question_columns = {column['name'] for column in inspector.get_columns('questions')}

    with db.engine.begin() as connection:
        if 'image_path' not in question_columns:
            connection.execute(text('ALTER TABLE questions ADD COLUMN image_path VARCHAR(255)'))
        if 'comment' not in question_columns:
            connection.execute(text('ALTER TABLE questions ADD COLUMN comment TEXT'))
        if 'secret_password' not in question_columns:
            connection.execute(text("ALTER TABLE questions ADD COLUMN secret_password VARCHAR(128) NOT NULL DEFAULT ''"))


def ensure_default_records() -> None:
    """Ensure singleton rows exist for settings and game state."""

    if not QuizSettings.query.get(1):
        db.session.add(QuizSettings(id=1, final_message=''))

    if not GameState.query.get(1):
        db.session.add(GameState(id=1, current_index=0))

    db.session.commit()


def save_uploaded_image(upload) -> str | None:
    """Persist an uploaded image and return the relative static path."""

    if not upload or not upload.filename:
        return None

    filename = secure_filename(upload.filename)
    if not filename:
        return None

    extension = os.path.splitext(filename)[1]
    unique_name = f"{uuid.uuid4().hex}{extension}"

    upload_folder = current_app.config.get('UPLOAD_FOLDER')
    os.makedirs(upload_folder, exist_ok=True)

    destination = os.path.join(upload_folder, unique_name)
    upload.save(destination)

    # Return path relative to the static folder so url_for can resolve it.
    return os.path.relpath(destination, os.path.join(os.getcwd(), 'static')).replace('\\', '/')


def register_routes(app: Flask) -> None:
    @app.route('/', methods=['GET', 'POST'])
    def quiz():
        questions = Question.query.options(joinedload(Question.options)).order_by(Question.id).all()
        if not questions:
            return render_template('empty_quiz.html')

        settings = QuizSettings.query.get(1)
        game_state = GameState.query.get(1)
        if not game_state:
            game_state = GameState(id=1, current_index=0)
            db.session.add(game_state)
            db.session.commit()

        if game_state.current_index >= len(questions):
            final_message = settings.final_message if settings and settings.final_message else 'أحسنت! لقد أكملت الرحلة السرية.'
            return render_template('final_message.html', final_message=final_message)

        question = questions[game_state.current_index]

        feedback = None
        is_correct = None
        show_password_gate = False
        password_error = None

        action = request.form.get('action') if request.method == 'POST' else None

        if request.method == 'POST' and action == 'answer':
            selected_option = request.form.get('answer')
            is_correct = selected_option == question.correct_answer
            if is_correct:
                feedback = 'إجابة صحيحة! أحسنت.'
                if question.secret_password:
                    show_password_gate = True
                else:
                    game_state.current_index += 1
                    db.session.commit()
                    return redirect(url_for('quiz'))
            else:
                feedback = 'إجابة غير صحيحة، حاول مرة أخرى!'

        elif request.method == 'POST' and action == 'password':
            entered_password = request.form.get('question_password', '').strip()
            if entered_password == (question.secret_password or ''):
                game_state.current_index += 1
                db.session.commit()
                return redirect(url_for('quiz'))
            else:
                feedback = 'إجابة صحيحة! أحسنت.'
                show_password_gate = True
                password_error = 'كلمة المرور غير صحيحة، حاول مرة أخرى.'
                is_correct = True

        incorrect_pool = [opt.text for opt in question.options if not opt.is_correct]
        random.shuffle(incorrect_pool)
        incorrect_choices = incorrect_pool[:3]

        if len(incorrect_choices) < 3:
            if incorrect_pool:
                incorrect_choices.extend(
                    random.choices(incorrect_pool, k=3 - len(incorrect_choices))
                )
            else:
                incorrect_choices.extend(['إجابة مختلفة'] * (3 - len(incorrect_choices)))

        all_choices = incorrect_choices[:3] + [question.correct_answer]
        random.shuffle(all_choices)

        return render_template(
            'quiz.html',
            question=question,
            options=all_choices,
            feedback=feedback,
            is_correct=is_correct,
            show_password_gate=show_password_gate,
            password_error=password_error,
        )

    @app.route('/admin', methods=['GET', 'POST'])
    def admin():
        if request.method == 'POST':
            form_type = request.form.get('form_type')

            if form_type == 'add_question':
                question_text = request.form.get('question_text')
                correct_answer = request.form.get('correct_answer')
                wrong_answers = request.form.get('wrong_answers', '')
                comment = request.form.get('comment')
                secret_password = request.form.get('secret_password', '').strip()
                image_url = request.form.get('image_url', '').strip()
                image_file = request.files.get('image_file')

                wrong_answers_list = [ans.strip() for ans in wrong_answers.split('\n') if ans.strip()]

                if len(wrong_answers_list) < 3:
                    flash('يجب إضافة ثلاث إجابات خاطئة على الأقل.', 'error')
                    return redirect(url_for('admin'))

                if not question_text or not correct_answer:
                    flash('يجب إدخال نص السؤال والإجابة الصحيحة.', 'error')
                    return redirect(url_for('admin'))

                if not secret_password:
                    flash('يجب تحديد كلمة مرور سرية للسؤال.', 'error')
                    return redirect(url_for('admin'))

                question = Question(
                    text=question_text,
                    correct_answer=correct_answer,
                    comment=comment,
                    secret_password=secret_password,
                )

                if image_file and image_file.filename:
                    saved_path = save_uploaded_image(image_file)
                    if saved_path:
                        question.image_path = saved_path
                elif image_url:
                    question.image_path = image_url

                db.session.add(question)
                db.session.flush()

                correct_option = AnswerOption(question_id=question.id, text=correct_answer, is_correct=True)
                db.session.add(correct_option)

                for answer in wrong_answers_list:
                    db.session.add(AnswerOption(question_id=question.id, text=answer, is_correct=False))

                db.session.commit()
                flash('تمت إضافة السؤال بنجاح.', 'success')
                return redirect(url_for('admin'))

            if form_type == 'update_settings':
                final_message = request.form.get('final_message', '')
                settings = QuizSettings.query.get(1)
                if not settings:
                    settings = QuizSettings(id=1)
                    db.session.add(settings)
                settings.final_message = final_message
                db.session.commit()
                flash('تم تحديث الرسالة النهائية.', 'success')
                return redirect(url_for('admin'))

        questions = Question.query.options(joinedload(Question.options)).all()
        settings = QuizSettings.query.get(1)
        game_state = GameState.query.get(1)
        total_questions = len(questions)
        current_index = game_state.current_index if game_state else 0

        return render_template(
            'admin.html',
            questions=questions,
            settings=settings,
            current_index=current_index,
            total_questions=total_questions,
        )

    @app.route('/admin/edit/<int:question_id>', methods=['GET', 'POST'])
    def edit_question(question_id):
        question = Question.query.options(joinedload(Question.options)).get_or_404(question_id)

        if request.method == 'POST':
            question_text = request.form.get('question_text')
            correct_answer = request.form.get('correct_answer')
            wrong_answers = request.form.getlist('wrong_answers')
            wrong_answers_list = [answer.strip() for answer in wrong_answers if answer.strip()]
            comment = request.form.get('comment')
            secret_password = request.form.get('secret_password', '').strip()
            image_url = request.form.get('image_url', '').strip()
            image_file = request.files.get('image_file')

            if not question_text or not correct_answer:
                flash('يجب إدخال نص السؤال والإجابة الصحيحة.', 'error')
                return redirect(url_for('edit_question', question_id=question.id))

            if len(wrong_answers_list) < 3:
                flash('يجب الاحتفاظ بثلاث إجابات خاطئة على الأقل.', 'error')
                return redirect(url_for('edit_question', question_id=question.id))

            if not secret_password:
                flash('يجب تحديد كلمة مرور سرية للسؤال.', 'error')
                return redirect(url_for('edit_question', question_id=question.id))

            question.text = question_text
            question.correct_answer = correct_answer
            question.comment = comment
            question.secret_password = secret_password

            if image_file and image_file.filename:
                saved_path = save_uploaded_image(image_file)
                if saved_path:
                    question.image_path = saved_path
            elif image_url:
                question.image_path = image_url

            AnswerOption.query.filter_by(question_id=question.id).delete()
            db.session.add(AnswerOption(question_id=question.id, text=correct_answer, is_correct=True))

            for answer_text in wrong_answers_list:
                db.session.add(AnswerOption(question_id=question.id, text=answer_text, is_correct=False))

            db.session.commit()
            flash('تم تحديث السؤال بنجاح.', 'success')
            return redirect(url_for('admin'))

        incorrect_options = [option.text for option in question.options if not option.is_correct]
        return render_template('edit_question.html', question=question, incorrect_options=incorrect_options)

    @app.route('/admin/reset', methods=['POST'])
    def reset_game():
        game_state = GameState.query.get(1)
        if not game_state:
            game_state = GameState(id=1, current_index=0)
            db.session.add(game_state)
        else:
            game_state.current_index = 0
        db.session.commit()
        flash('تمت إعادة ضبط تقدم اللعبة.', 'success')
        return redirect(url_for('admin'))


app = create_app()


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)))
